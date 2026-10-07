from dataclasses import replace
from datetime import datetime
from uuid import UUID

from app_foundation.notification import (
    Delivery,
    Notification,
    NotificationChannel,
    NotificationPreference,
)
from app_foundation.primitives import OrganizationId, PageRequest, UserId


class MemoryNotificationRepository:
    def __init__(self) -> None:
        self.notifications: dict[UUID, Notification] = {}
        self.deliveries: dict[UUID, Delivery] = {}
        self.preferences: dict[tuple[UserId, NotificationChannel], bool] = {}

    async def add(self, notification: Notification) -> None:
        self.notifications[notification.id] = notification

    async def get(
        self, organization_id: OrganizationId, user_id: UserId, notification_id: UUID
    ) -> Notification | None:
        n = self.notifications.get(notification_id)
        return (
            n
            if n
            and n.visible_in_app
            and n.organization_id == organization_id
            and n.recipient_id == user_id
            else None
        )

    async def list(
        self, organization_id: OrganizationId, user_id: UserId, page: PageRequest
    ) -> tuple[Notification, ...]:
        items = sorted(
            (
                n
                for n in self.notifications.values()
                if n.visible_in_app
                and n.organization_id == organization_id
                and n.recipient_id == user_id
            ),
            key=lambda n: n.id,
            reverse=True,
        )
        return tuple(items[page.offset : page.offset + page.limit])

    async def mark_read(
        self,
        organization_id: OrganizationId,
        user_id: UserId,
        notification_id: UUID | None,
        at: datetime,
    ) -> None:
        for key, n in tuple(self.notifications.items()):
            if (
                n.organization_id == organization_id
                and n.recipient_id == user_id
                and (notification_id is None or key == notification_id)
                and n.read_at is None
            ):
                self.notifications[key] = replace(n, read_at=at)

    async def save_preference(self, preference: NotificationPreference) -> None:
        self.preferences[preference.user_id, preference.channel] = preference.enabled

    async def enabled(self, user_id: UserId, channel: NotificationChannel) -> bool:
        return self.preferences.get((user_id, channel), True)

    async def enqueue(self, delivery: Delivery) -> None:
        self.deliveries[delivery.id] = delivery

    async def pending(self, now: datetime, limit: int) -> tuple[Delivery, ...]:
        return tuple(
            d
            for d in self.deliveries.values()
            if d.delivered_at is None and d.attempts < 5 and d.available_at <= now
        )[:limit]

    async def save_delivery(self, delivery: Delivery) -> None:
        self.deliveries[delivery.id] = delivery
