from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.notification import (
    Delivery,
    Notification,
    NotificationChannel,
    NotificationPreference,
)
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import OrganizationId, PageRequest, UserId


class NotificationRecord(Base):
    __tablename__ = "af_notifications"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_organizations.id"), index=True
    )
    recipient_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), index=True)
    visible_in_app: Mapped[bool]
    title: Mapped[str]
    body: Mapped[str]
    notification_type: Mapped[str]
    created_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    read_at: Mapped[datetime | None] = MappedColumn[datetime | None](DateTime(timezone=True))
    action_metadata: Mapped[list[list[str]]] = MappedColumn[list[list[str]]](JSON)


class PreferenceRecord(Base):
    __tablename__ = "af_notification_preferences"
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), primary_key=True)
    channel: Mapped[str] = MappedColumn[str](primary_key=True)
    enabled: Mapped[bool]


class DeliveryRecord(Base):
    __tablename__ = "af_notification_deliveries"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    notification_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_notifications.id"))
    channel: Mapped[str]
    recipient: Mapped[str]
    title: Mapped[str]
    body: Mapped[str]
    available_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True), index=True)
    attempts: Mapped[int]
    delivered_at: Mapped[datetime | None] = MappedColumn[datetime | None](DateTime(timezone=True))
    last_error: Mapped[str | None]


def _notification(r: NotificationRecord) -> Notification:
    return Notification(
        r.id,
        OrganizationId(r.organization_id),
        UserId(r.recipient_id),
        r.title,
        r.body,
        r.notification_type,
        r.created_at,
        r.read_at,
        tuple((k, v) for k, v in r.action_metadata),
        r.visible_in_app,
    )


def _delivery(r: DeliveryRecord) -> Delivery:
    return Delivery(
        r.id,
        r.notification_id,
        NotificationChannel(r.channel),
        r.recipient,
        r.title,
        r.body,
        r.available_at,
        r.attempts,
        r.delivered_at,
        r.last_error,
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> None:
        async with translate_errors():
            self._session.add(
                NotificationRecord(
                    id=notification.id,
                    organization_id=notification.organization_id,
                    recipient_id=notification.recipient_id,
                    visible_in_app=notification.visible_in_app,
                    title=notification.title,
                    body=notification.body,
                    notification_type=notification.notification_type,
                    created_at=notification.created_at,
                    read_at=notification.read_at,
                    action_metadata=[list(p) for p in notification.metadata],
                )
            )
            await self._session.flush()

    async def get(
        self, organization_id: OrganizationId, user_id: UserId, notification_id: UUID
    ) -> Notification | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(NotificationRecord).where(
                    NotificationRecord.id == notification_id,
                    NotificationRecord.organization_id == organization_id,
                    NotificationRecord.recipient_id == user_id,
                    NotificationRecord.visible_in_app.is_(True),
                )
            )
            return _notification(r) if r else None

    async def list(
        self, organization_id: OrganizationId, user_id: UserId, page: PageRequest
    ) -> tuple[Notification, ...]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(NotificationRecord)
                .where(
                    NotificationRecord.organization_id == organization_id,
                    NotificationRecord.recipient_id == user_id,
                    NotificationRecord.visible_in_app.is_(True),
                )
                .order_by(NotificationRecord.id.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
            return tuple(_notification(r) for r in rows)

    async def mark_read(
        self,
        organization_id: OrganizationId,
        user_id: UserId,
        notification_id: UUID | None,
        at: datetime,
    ) -> None:
        async with translate_errors():
            statement = update(NotificationRecord).where(
                NotificationRecord.organization_id == organization_id,
                NotificationRecord.recipient_id == user_id,
                NotificationRecord.read_at.is_(None),
            )
            if notification_id:
                statement = statement.where(NotificationRecord.id == notification_id)
            await self._session.execute(statement.values(read_at=at))

    async def save_preference(self, preference: NotificationPreference) -> None:
        async with translate_errors():
            await self._session.merge(
                PreferenceRecord(
                    user_id=preference.user_id,
                    channel=preference.channel.value,
                    enabled=preference.enabled,
                )
            )
            await self._session.flush()

    async def enabled(self, user_id: UserId, channel: NotificationChannel) -> bool:
        async with translate_errors():
            r = await self._session.get(PreferenceRecord, (user_id, channel.value))
            return r.enabled if r else True

    async def enqueue(self, delivery: Delivery) -> None:
        await self.save_delivery(delivery)

    async def pending(self, now: datetime, limit: int) -> tuple[Delivery, ...]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(DeliveryRecord)
                .where(
                    DeliveryRecord.available_at <= now,
                    DeliveryRecord.delivered_at.is_(None),
                    DeliveryRecord.attempts < 5,
                )
                .order_by(DeliveryRecord.available_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            return tuple(_delivery(r) for r in rows)

    async def save_delivery(self, delivery: Delivery) -> None:
        async with translate_errors():
            await self._session.merge(
                DeliveryRecord(
                    id=delivery.id,
                    notification_id=delivery.notification_id,
                    channel=delivery.channel.value,
                    recipient=delivery.recipient,
                    title=delivery.title,
                    body=delivery.body,
                    available_at=delivery.available_at,
                    attempts=delivery.attempts,
                    delivered_at=delivery.delivered_at,
                    last_error=delivery.last_error,
                )
            )
            await self._session.flush()
