from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app_foundation.events import ApplicationEvent, EventPublisher
from app_foundation.primitives import (
    Clock,
    FoundationError,
    IdGenerator,
    Metadata,
    NotFound,
    OrganizationId,
    PageRequest,
    UserId,
)


class NotificationChannel(StrEnum):
    IN_APP = "in-app"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


@dataclass(frozen=True, slots=True)
class NotificationRecipient:
    user_id: UserId
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    user_id: UserId
    channel: NotificationChannel
    enabled: bool


@dataclass(frozen=True, slots=True)
class Notification:
    id: UUID
    organization_id: OrganizationId
    recipient_id: UserId
    title: str
    body: str
    notification_type: str
    created_at: datetime
    read_at: datetime | None = None
    metadata: Metadata = ()
    visible_in_app: bool = True


@dataclass(frozen=True, slots=True)
class Delivery:
    id: UUID
    notification_id: UUID
    channel: NotificationChannel
    recipient: str
    title: str
    body: str
    available_at: datetime
    attempts: int = 0
    delivered_at: datetime | None = None
    last_error: str | None = None


class NotificationRepository(Protocol):
    async def add(self, notification: Notification) -> None: ...
    async def get(
        self, organization_id: OrganizationId, user_id: UserId, notification_id: UUID
    ) -> Notification | None: ...
    async def list(
        self, organization_id: OrganizationId, user_id: UserId, page: PageRequest
    ) -> tuple[Notification, ...]: ...
    async def mark_read(
        self,
        organization_id: OrganizationId,
        user_id: UserId,
        notification_id: UUID | None,
        at: datetime,
    ) -> None: ...
    async def save_preference(self, preference: NotificationPreference) -> None: ...
    async def enabled(self, user_id: UserId, channel: NotificationChannel) -> bool: ...
    async def enqueue(self, delivery: Delivery) -> None: ...
    async def pending(self, now: datetime, limit: int) -> tuple[Delivery, ...]: ...
    async def save_delivery(self, delivery: Delivery) -> None: ...


class NotificationTransport(Protocol):
    async def deliver(self, delivery: Delivery) -> None: ...


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        clock: Clock,
        ids: IdGenerator,
        events: EventPublisher,
    ) -> None:
        self.repository = repository
        self._clock = clock
        self._ids = ids
        self._events = events

    async def create(
        self,
        organization_id: OrganizationId,
        recipient: NotificationRecipient,
        title: str,
        body: str,
        notification_type: str,
        channels: tuple[NotificationChannel, ...] = (NotificationChannel.IN_APP,),
        metadata: Metadata = (),
    ) -> Notification:
        notification = Notification(
            self._ids.new(),
            organization_id,
            recipient.user_id,
            title,
            body,
            notification_type,
            self._clock.now(),
            metadata=metadata,
            visible_in_app=NotificationChannel.IN_APP in channels
            and await self.repository.enabled(recipient.user_id, NotificationChannel.IN_APP),
        )
        # Persist the message as the delivery source even if the in-app preference is disabled.
        await self.repository.add(notification)
        for channel in dict.fromkeys(channels):
            if not await self.repository.enabled(recipient.user_id, channel):
                continue
            address = recipient.email if channel == NotificationChannel.EMAIL else recipient.phone
            if channel != NotificationChannel.IN_APP and address:
                await self.repository.enqueue(
                    Delivery(
                        self._ids.new(),
                        notification.id,
                        channel,
                        address,
                        title,
                        body,
                        self._clock.now(),
                    )
                )
        if notification.visible_in_app:
            await self._events.publish(
                (
                    ApplicationEvent(
                        "notification.created",
                        notification.id,
                        notification.created_at,
                        (
                            ("user_id", str(recipient.user_id)),
                            ("organization_id", str(organization_id)),
                        ),
                    ),
                )
            )
        return notification

    async def mark_read(
        self, organization_id: OrganizationId, user_id: UserId, notification_id: UUID | None = None
    ) -> None:
        if notification_id and not await self.repository.get(
            organization_id, user_id, notification_id
        ):
            raise NotFound("Notification not found")
        await self.repository.mark_read(
            organization_id, user_id, notification_id, self._clock.now()
        )

    async def deliver_pending(self, transport: NotificationTransport, limit: int = 50) -> None:
        for delivery in await self.repository.pending(self._clock.now(), limit):
            try:
                await transport.deliver(delivery)
            except FoundationError as error:
                # Never persist transport exception messages: they may contain provider secrets.
                await self.repository.save_delivery(
                    replace(
                        delivery,
                        attempts=delivery.attempts + 1,
                        available_at=self._clock.now()
                        + timedelta(seconds=30 * 2**delivery.attempts),
                        last_error=type(error).__name__,
                    )
                )
            else:
                await self.repository.save_delivery(
                    replace(
                        delivery,
                        attempts=delivery.attempts + 1,
                        delivered_at=self._clock.now(),
                        last_error=None,
                    )
                )


__all__ = (
    "Delivery",
    "Notification",
    "NotificationChannel",
    "NotificationPreference",
    "NotificationRecipient",
    "NotificationRepository",
    "NotificationService",
    "NotificationTransport",
)
