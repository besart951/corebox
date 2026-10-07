from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app_foundation.access_control import (
    Authorizer,
    OwnerPolicy,
    Principal,
    Resource,
    Role,
    RoleRepository,
)
from app_foundation.access_control.sqlalchemy import SqlAlchemyRoleRepository
from app_foundation.api import bearer
from app_foundation.auth import AuthService
from app_foundation.auth.adapters import Argon2PasswordHasher, JwtTokenIssuer
from app_foundation.auth.email import QueuedVerificationSender
from app_foundation.auth.mfa import MfaService
from app_foundation.auth.protocols import RateLimiter
from app_foundation.auth.sqlalchemy import SqlAlchemyAuthRepository
from app_foundation.config import JwtSettings
from app_foundation.events import ApplicationEvent, Event, EventPublisher
from app_foundation.identity import UserService
from app_foundation.identity.sqlalchemy import SqlAlchemyUserRepository
from app_foundation.notification import NotificationService
from app_foundation.notification.sqlalchemy import SqlAlchemyNotificationRepository
from app_foundation.observability import AuditRecord
from app_foundation.observability.sqlalchemy import SqlAlchemyAuditSink
from app_foundation.organization import OrganizationService
from app_foundation.organization.sqlalchemy import SqlAlchemyOrganizationRepository
from app_foundation.persistence import Transaction
from app_foundation.primitives import (
    OrganizationId,
    PermissionDenied,
    SystemClock,
    UserId,
    UUID7Generator,
)
from app_foundation.realtime import RealtimeEvent
from app_foundation.realtime.memory import MemoryRealtimeBroker

from .settings import Settings


class RealtimeEvents:
    def __init__(self, broker: MemoryRealtimeBroker) -> None:
        self._broker = broker

    async def publish(self, events: tuple[Event, ...]) -> None:
        for event in events:
            if isinstance(event, ApplicationEvent) and event.event_name == "notification.created":
                metadata = dict(event.metadata)
                await self._broker.publish(
                    RealtimeEvent(
                        event.entity_id,
                        f"notifications:{metadata['organization_id']}:{metadata['user_id']}",
                        event.event_name,
                        event.occurred_at,
                        event.metadata,
                    )
                )


class AuditedEvents:
    def __init__(self, sink: SqlAlchemyAuditSink, events: EventPublisher) -> None:
        self._sink = sink
        self._events = events

    async def publish(self, events: tuple[Event, ...]) -> None:
        for event in events:
            if isinstance(event, ApplicationEvent):
                await self._sink.append(
                    AuditRecord(
                        UUID7Generator().new(),
                        event.event_name,
                        event.occurred_at,
                        None,
                        None,
                        event.entity_id,
                        event.metadata,
                    )
                )
        await self._events.publish(events)


@dataclass(frozen=True, slots=True)
class Operation:
    """Explicit composition record, not a service registry."""

    users: UserService
    auth: AuthService
    mfa: MfaService
    organizations: OrganizationService
    roles: RoleRepository
    authorizer: Authorizer
    notifications: NotificationService
    verification_sender: QueuedVerificationSender
    session: AsyncSession
    events: EventPublisher


class Composition:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        limiter: RateLimiter,
        broker: MemoryRealtimeBroker,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.clock = SystemClock()
        self.ids = UUID7Generator()
        self.limiter = limiter
        self.broker = broker
        self.passwords = Argon2PasswordHasher()
        self.tokens = JwtTokenIssuer(JwtSettings(secret=settings.jwt_secret), self.clock)

    @asynccontextmanager
    async def operation(self) -> AsyncIterator[Operation]:
        async with self.sessions() as session:
            transaction = Transaction(session, RealtimeEvents(self.broker))
            async with transaction.begin():
                events = AuditedEvents(SqlAlchemyAuditSink(session), transaction)
                users = UserService(SqlAlchemyUserRepository(session), self.clock, self.ids, events)
                auth_repository = SqlAlchemyAuthRepository(session)
                key = self.settings.encryption_key.get_secret_value().encode()
                sender = QueuedVerificationSender(session, key, self.clock)
                auth = AuthService(
                    users,
                    auth_repository,
                    self.passwords,
                    self.tokens,
                    self.limiter,
                    sender,
                    self.clock,
                    self.ids,
                    events,
                )
                mfa = MfaService(auth_repository, self.passwords, self.limiter, key, self.clock)
                organizations = OrganizationService(
                    SqlAlchemyOrganizationRepository(session), self.clock, self.ids, events
                )
                roles = SqlAlchemyRoleRepository(session)
                authorizer = Authorizer(
                    roles,
                    organizations.repository,
                    (OwnerPolicy(frozenset({"user.read", "user.write"})),),
                )
                notifications = NotificationService(
                    SqlAlchemyNotificationRepository(session), self.clock, self.ids, events
                )
                yield Operation(
                    users,
                    auth,
                    mfa,
                    organizations,
                    roles,
                    authorizer,
                    notifications,
                    sender,
                    session,
                    events,
                )

    @asynccontextmanager
    async def users(self) -> AsyncIterator[UserService]:
        async with self.operation() as operation:
            yield operation.users

    @asynccontextmanager
    async def auth(self) -> AsyncIterator[AuthService]:
        async with self.operation() as operation:
            yield operation.auth

    @asynccontextmanager
    async def mfa(self) -> AsyncIterator[tuple[AuthService, MfaService]]:
        async with self.operation() as operation:
            yield operation.auth, operation.mfa

    @asynccontextmanager
    async def organizations(self) -> AsyncIterator[tuple[OrganizationService, RoleRepository]]:
        async with self.operation() as operation:
            yield operation.organizations, operation.roles

    @asynccontextmanager
    async def notifications(self) -> AsyncIterator[NotificationService]:
        async with self.operation() as operation:
            yield operation.notifications

    async def authenticate(self, header: str) -> Principal:
        async with self.auth() as auth:
            return Principal((await auth.authenticate(bearer(header))).id)

    async def authorize(self, header: str, permission: str, resource: Resource) -> Principal:
        async with self.operation() as operation:
            principal = Principal((await operation.auth.authenticate(bearer(header))).id)
            await operation.authorizer.require(principal, permission, resource)
            return principal

    async def authorize_topic(self, header: str, topic: str) -> None:
        parts = topic.split(":")
        if len(parts) != 3 or parts[0] != "notifications":
            raise PermissionDenied("Unknown topic")
        try:
            organization_id, user_id = OrganizationId(UUID(parts[1])), UserId(UUID(parts[2]))
        except ValueError as error:
            raise PermissionDenied("Invalid topic") from error
        principal = await self.authorize(header, "notification.read", Resource(organization_id))
        if principal.user_id != user_id:
            raise PermissionDenied("Topic belongs to another user")

    async def seed_roles(self) -> None:
        basic = frozenset({"team.read", "notification.read", "billing.read"})
        admin = basic | {"team.write", "membership.manage", "billing.manage"}
        async with self.operation() as operation:
            for name, permissions in (
                ("owner", admin),
                ("admin", admin),
                ("member", basic),
                ("viewer", basic),
            ):
                await operation.roles.save_role(Role(name, permissions))
