import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app_foundation.api import RequestIdMiddleware, install_exception_handlers
from app_foundation.auth.api import create_auth_router, create_mfa_router
from app_foundation.auth.rate_limit import PostgresRateLimiter
from app_foundation.communication.email import EmailAddress, EmailSender, MemoryEmailSender
from app_foundation.communication.email.smtp import SmtpEmailSender
from app_foundation.config import EmailSettings
from app_foundation.identity.api import create_user_router
from app_foundation.jobs import FunctionJob, IntervalSchedule, JobRegistry, JobRunner, Scheduler
from app_foundation.jobs.postgres import PostgresLock
from app_foundation.notification.api import create_notification_router
from app_foundation.notification.transports import CommunicationTransport
from app_foundation.organization.api import create_organization_router, create_team_router
from app_foundation.persistence import create_database
from app_foundation.primitives import SystemClock
from app_foundation.realtime.memory import MemoryRealtimeBroker
from app_foundation.realtime.sse import create_sse_router
from app_foundation.realtime.websocket import create_websocket_router

from .container import Composition
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, sessions = create_database(settings.database_url.get_secret_value())
    clock = SystemClock()
    limiter = PostgresRateLimiter(sessions, clock)
    composition = Composition(sessions, settings, limiter, MemoryRealtimeBroker())
    email: EmailSender = (
        SmtpEmailSender(
            EmailSettings(host=settings.smtp_host, port=settings.smtp_port, _env_file=".env")
        )
        if settings.smtp_host
        else MemoryEmailSender()
    )

    async def deliveries() -> None:
        async with composition.operation() as operation:
            await operation.verification_sender.deliver_pending(
                email, EmailAddress(settings.sender_email), settings.public_url
            )
            await operation.notifications.deliver_pending(
                CommunicationTransport(EmailAddress(settings.sender_email), email)
            )

    async def cleanup() -> None:
        async with composition.auth() as auth:
            await auth.repository.delete_expired_sessions(clock.now())
        await limiter.cleanup()

    registry = JobRegistry(
        (FunctionJob("notification.deliver", deliveries), FunctionJob("auth.cleanup", cleanup))
    )
    scheduler = Scheduler(
        JobRunner(registry, PostgresLock(engine)),
        (("notification.deliver", IntervalSchedule(5)), ("auth.cleanup", IntervalSchedule(300))),
        clock,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await composition.seed_roles()
        task = asyncio.create_task(scheduler.run()) if settings.jobs_enabled else None
        try:
            yield
        finally:
            scheduler.stop()
            if task:
                await task
            await engine.dispose()

    app = FastAPI(title="Foundation consumer example", lifespan=lifespan)
    install_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )
    app.include_router(create_auth_router(composition.auth))
    app.include_router(create_mfa_router(composition.mfa, composition.authenticate, "Example"))
    app.include_router(create_user_router(composition.users, composition.authorize))
    app.include_router(
        create_organization_router(
            composition.organizations,
            composition.authenticate,
            composition.authorize,
            composition.users,
        )
    )
    app.include_router(create_team_router(composition.organizations, composition.authorize))
    app.include_router(create_notification_router(composition.notifications, composition.authorize))
    app.include_router(create_sse_router(composition.broker, composition.authorize_topic))
    app.include_router(create_websocket_router(composition.broker, composition.authorize_topic))
    if settings.stripe_enabled or settings.google_enabled:
        from .providers import install_providers

        install_providers(app, composition)

    @app.get("/health")
    async def health() -> dict[str, str]:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app
