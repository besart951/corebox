import asyncio
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app_foundation.auth import AuthenticationRejected, InvalidCredentials, TokenPair
from app_foundation.auth.adapters import MemoryRateLimiter
from app_foundation.auth.email import VerificationDeliveryRecord
from app_foundation.auth.models import RateLimitExceeded
from app_foundation.auth.rate_limit import PostgresRateLimiter
from app_foundation.billing import BillingService, PaymentEvent
from app_foundation.billing.memory import FakePaymentProvider
from app_foundation.billing.sqlalchemy import SqlAlchemyBillingRepository
from app_foundation.events import InProcessEventPublisher
from app_foundation.identity import EmailAlreadyExists
from app_foundation.jobs.postgres import PostgresLock
from app_foundation.persistence import Base
from app_foundation.persistence.migrations.versions import (
    af0001_initial_foundation_schema as initial,
)
from app_foundation.persistence.migrations.versions import (
    af0002_tenant_constraints_and_notification_ as second,
)
from app_foundation.primitives import (
    FixedClock,
    NotFound,
    OrganizationId,
    SystemClock,
    UserId,
    UUID7Generator,
)
from app_foundation.realtime.memory import MemoryRealtimeBroker
from examples.example_app.container import Composition
from examples.example_app.settings import Settings

pytestmark = pytest.mark.postgres

type Database = tuple[AsyncEngine, async_sessionmaker[AsyncSession]]


def composition(database: Database) -> Composition:
    return Composition(
        database[1],
        Settings(
            database_url=SecretStr("unused"),
            jwt_secret=SecretStr("x" * 40),
            encryption_key=SecretStr(Fernet.generate_key().decode()),
            jobs_enabled=False,
        ),
        MemoryRateLimiter(SystemClock(), limit=100),
        MemoryRealtimeBroker(),
    )


async def registered(app: Composition) -> UserId:
    async with app.operation() as operation:
        user = await operation.auth.register("person@example.com", "correct-password", "Person")
        row = await operation.session.scalar(select(VerificationDeliveryRecord))
        assert row is not None
        token = (
            Fernet(app.settings.encryption_key.get_secret_value().encode())
            .decrypt(row.encrypted_token.encode())
            .decode()
        )
        await operation.auth.verify_email(token)
        return user.id


async def test_migration_matches_models_and_reversible(database: Database) -> None:
    def validate(connection: Connection) -> None:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
        with Operations.context(context):
            second.downgrade()
            initial.downgrade()
            assert not inspect(connection).get_table_names()
            initial.upgrade()
            second.upgrade()
        assert compare_metadata(context, Base.metadata) == []

    async with database[0].begin() as connection:
        await connection.run_sync(validate)


async def test_transaction_rollback_and_unique_email_race(database: Database) -> None:
    app = composition(database)
    with pytest.raises(RuntimeError):
        async with app.users() as users:
            await users.create("rollback@example.com", "Rollback")
            raise RuntimeError("Rollback requested")
    async with app.users() as users:
        assert await users.repository.get_by_email("rollback@example.com") is None

    async def create() -> bool:
        try:
            async with app.users() as users:
                await users.create("race@example.com", "Race")
        except EmailAlreadyExists:
            return False
        return True

    results = await asyncio.gather(create(), create())
    assert sorted(results) == [False, True]


async def test_refresh_rotation_concurrent_reuse_revokes_family(database: Database) -> None:
    app = composition(database)
    await registered(app)
    async with app.auth() as auth:
        pair = await auth.login("person@example.com", "correct-password")
    assert isinstance(pair, TokenPair)

    async def rotate() -> TokenPair | AuthenticationRejected:
        async with app.auth() as auth:
            return await auth.refresh(pair.refresh_token)

    outcomes = await asyncio.gather(rotate(), rotate())
    successes = [o for o in outcomes if isinstance(o, TokenPair)]
    assert len(successes) == 1
    assert sum(isinstance(o, AuthenticationRejected) for o in outcomes) == 1
    async with app.auth() as auth:
        with pytest.raises(InvalidCredentials):
            await auth.authenticate(successes[0].access_token)


async def test_password_reset_concurrent_consumption(database: Database) -> None:
    app = composition(database)
    await registered(app)
    async with app.operation() as operation:
        await operation.auth.request_verification("person@example.com", "reset-password")
        row = await operation.session.scalar(
            select(VerificationDeliveryRecord).where(
                VerificationDeliveryRecord.purpose == "reset-password"
            )
        )
        assert row is not None
        token = (
            Fernet(app.settings.encryption_key.get_secret_value().encode())
            .decrypt(row.encrypted_token.encode())
            .decode()
        )

    async def reset() -> bool:
        try:
            async with app.auth() as auth:
                await auth.reset_password(token, "replacement-password")
        except InvalidCredentials:
            return False
        return True

    assert sorted(await asyncio.gather(reset(), reset())) == [False, True]


async def test_rate_limit_persists_and_job_lock_excludes(database: Database) -> None:
    limiter = PostgresRateLimiter(
        database[1], FixedClock(datetime(2026, 1, 1, tzinfo=UTC)), limit=1
    )
    await limiter.require("key")
    with pytest.raises(RateLimitExceeded):
        await limiter.require("key")
    lock = PostgresLock(database[0])
    async with lock.acquire("job") as first:
        assert first
        async with lock.acquire("job") as second:
            assert not second
    async with lock.acquire("job") as third:
        assert third


async def test_webhook_concurrent_deduplication_and_tenant_scope(database: Database) -> None:
    app = composition(database)
    user = await registered(app)
    async with app.organizations() as (organizations, _):
        org = await organizations.create("Org", user)
    provider = FakePaymentProvider()
    async with database[1].begin() as session:
        service = BillingService(
            SqlAlchemyBillingRepository(session),
            provider,
            UUID7Generator(),
            SystemClock(),
            InProcessEventPublisher(),
        )
        await service.create_customer(org.id, "billing@example.com")
        subscription = await service.subscribe(org.id, "price", uuid7())
    provider.events[b"event"] = PaymentEvent(
        "event1", "customer.subscription.updated", subscription.provider_id
    )

    async def process() -> bool:
        async with database[1].begin() as session:
            service = BillingService(
                SqlAlchemyBillingRepository(session),
                provider,
                UUID7Generator(),
                SystemClock(),
                InProcessEventPublisher(),
            )
            return await service.webhook(b"event", "fake-valid-signature")

    assert sorted(await asyncio.gather(process(), process())) == [False, True]
    async with database[1].begin() as session:
        service = BillingService(
            SqlAlchemyBillingRepository(session),
            provider,
            UUID7Generator(),
            SystemClock(),
            InProcessEventPublisher(),
        )
        with pytest.raises(NotFound):
            await service.cancel(OrganizationId(uuid7()), subscription.id)
        count = await session.scalar(text("SELECT count(*) FROM af_payment_events"))
        assert count == 1


async def test_mfa_recovery_code_consumed_once_across_transactions(database: Database) -> None:
    from app_foundation.auth.models import MfaEnrollment
    from app_foundation.auth.service import token_digest

    app = composition(database)
    user = await registered(app)
    key = app.settings.encryption_key.get_secret_value().encode()
    recovery = "random-recovery-code-for-test"
    async with app.auth() as auth:
        await auth.repository.save_mfa(
            MfaEnrollment(
                user,
                Fernet(key).encrypt(b"JBSWY3DPEHPK3PXP").decode(),
                True,
                (token_digest(recovery),),
            )
        )

    async def verify() -> bool:
        async with app.mfa() as (_, mfa):
            return await mfa.verify(user, recovery)

    assert sorted(await asyncio.gather(verify(), verify())) == [False, True]


async def test_notification_delivery_is_transactional_and_hidden_when_disabled(
    database: Database,
) -> None:
    from app_foundation.notification import (
        NotificationChannel,
        NotificationPreference,
        NotificationRecipient,
    )
    from app_foundation.primitives import PageRequest

    app = composition(database)
    user = await registered(app)
    async with app.organizations() as (organizations, _):
        organization = await organizations.create("Notify", user)
    with pytest.raises(RuntimeError):
        async with app.notifications() as notifications:
            await notifications.create(
                organization.id,
                NotificationRecipient(user, "person@example.com"),
                "Rolled back",
                "Body",
                "test",
                (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
            )
            raise RuntimeError("Rollback requested")
    async with app.operation() as operation:
        assert (
            await operation.notifications.repository.list(organization.id, user, PageRequest())
            == ()
        )
        assert await operation.notifications.repository.pending(app.clock.now(), 50) == ()
        await operation.notifications.repository.save_preference(
            NotificationPreference(user, NotificationChannel.IN_APP, False)
        )
        await operation.notifications.create(
            organization.id,
            NotificationRecipient(user, "person@example.com"),
            "Email only",
            "Body",
            "test",
            (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
        )
    async with app.notifications() as notifications:
        assert await notifications.repository.list(organization.id, user, PageRequest()) == ()
        assert len(await notifications.repository.pending(app.clock.now(), 50)) == 1
