from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import OrganizationId
from app_foundation.scheduling import CalendarEvent, Recurrence, Reminder, ReminderStatus


class ReminderRecord(Base):
    __tablename__ = "af_reminders"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_organizations.id"), index=True
    )
    title: Mapped[str]
    due_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True), index=True)
    timezone: Mapped[str]
    entity_reference: Mapped[str]
    description: Mapped[str]
    recurrence: Mapped[str]
    status: Mapped[str]


class CalendarEventRecord(Base):
    __tablename__ = "af_calendar_events"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_organizations.id"), index=True
    )
    title: Mapped[str]
    starts_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    ends_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    timezone: Mapped[str]
    description: Mapped[str]


def _reminder(r: ReminderRecord) -> Reminder:
    return Reminder(
        r.id,
        OrganizationId(r.organization_id),
        r.title,
        r.due_at,
        r.timezone,
        r.entity_reference,
        r.description,
        Recurrence(r.recurrence),
        ReminderStatus(r.status),
    )


class SqlAlchemyReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, reminder: Reminder) -> None:
        async with translate_errors():
            await self._session.merge(
                ReminderRecord(
                    id=reminder.id,
                    organization_id=reminder.organization_id,
                    title=reminder.title,
                    due_at=reminder.due_at,
                    timezone=reminder.timezone,
                    entity_reference=reminder.entity_reference,
                    description=reminder.description,
                    recurrence=reminder.recurrence.value,
                    status=reminder.status.value,
                )
            )
            await self._session.flush()

    async def get(self, organization_id: OrganizationId, reminder_id: UUID) -> Reminder | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(ReminderRecord).where(
                    ReminderRecord.id == reminder_id,
                    ReminderRecord.organization_id == organization_id,
                )
            )
            return _reminder(r) if r else None

    async def due(self, now: datetime, limit: int) -> tuple[Reminder, ...]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(ReminderRecord)
                .where(
                    ReminderRecord.due_at <= now,
                    ReminderRecord.status == ReminderStatus.PENDING.value,
                )
                .order_by(ReminderRecord.due_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            return tuple(_reminder(r) for r in rows)

    async def save_event(self, event: CalendarEvent) -> None:
        async with translate_errors():
            await self._session.merge(
                CalendarEventRecord(
                    id=event.id,
                    organization_id=event.organization_id,
                    title=event.title,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    timezone=event.timezone,
                    description=event.description,
                )
            )
            await self._session.flush()

    async def events(
        self, organization_id: OrganizationId, start: datetime, end: datetime
    ) -> tuple[CalendarEvent, ...]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(CalendarEventRecord).where(
                    CalendarEventRecord.organization_id == organization_id,
                    CalendarEventRecord.starts_at < end,
                    CalendarEventRecord.ends_at > start,
                )
            )
            return tuple(
                CalendarEvent(
                    r.id,
                    OrganizationId(r.organization_id),
                    r.title,
                    r.starts_at,
                    r.ends_at,
                    r.timezone,
                    r.description,
                )
                for r in rows
            )
