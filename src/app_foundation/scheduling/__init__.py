from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app_foundation.primitives import (
    Clock,
    IdGenerator,
    NotFound,
    OrganizationId,
    ValidationError,
    require_aware,
)


class Recurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: UUID
    organization_id: OrganizationId
    title: str
    starts_at: datetime
    ends_at: datetime
    timezone: str = "UTC"
    description: str = ""

    def __post_init__(self) -> None:
        require_aware(self.starts_at)
        require_aware(self.ends_at)
        ZoneInfo(self.timezone)
        if self.ends_at <= self.starts_at:
            raise ValidationError("Event must end after it starts")


@dataclass(frozen=True, slots=True)
class Reminder:
    id: UUID
    organization_id: OrganizationId
    title: str
    due_at: datetime
    timezone: str
    entity_reference: str
    description: str = ""
    recurrence: Recurrence = Recurrence.ONCE
    status: ReminderStatus = ReminderStatus.PENDING

    def __post_init__(self) -> None:
        require_aware(self.due_at)
        ZoneInfo(self.timezone)
        if not self.title.strip():
            raise ValidationError("Reminder title is required")


class ReminderRepository(Protocol):
    async def save(self, reminder: Reminder) -> None: ...
    async def get(self, organization_id: OrganizationId, reminder_id: UUID) -> Reminder | None: ...
    async def due(self, now: datetime, limit: int) -> tuple[Reminder, ...]: ...
    async def save_event(self, event: CalendarEvent) -> None: ...
    async def events(
        self, organization_id: OrganizationId, start: datetime, end: datetime
    ) -> tuple[CalendarEvent, ...]: ...


class ReminderTrigger(Protocol):
    async def trigger(self, reminder: Reminder) -> None: ...


class ReminderService:
    def __init__(
        self,
        repository: ReminderRepository,
        trigger: ReminderTrigger,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.repository = repository
        self._trigger = trigger
        self._clock = clock
        self._ids = ids

    async def create(
        self,
        organization_id: OrganizationId,
        title: str,
        due_at: datetime,
        timezone: str = "UTC",
        entity_reference: str = "",
        description: str = "",
        recurrence: Recurrence = Recurrence.ONCE,
    ) -> Reminder:
        reminder = Reminder(
            self._ids.new(),
            organization_id,
            title,
            due_at.astimezone(UTC),
            timezone,
            entity_reference,
            description,
            recurrence,
        )
        require_aware(due_at)
        await self.repository.save(reminder)
        return reminder

    async def cancel(self, organization_id: OrganizationId, reminder_id: UUID) -> None:
        reminder = await self.repository.get(organization_id, reminder_id)
        if reminder is None:
            raise NotFound("Reminder not found")
        await self.repository.save(replace(reminder, status=ReminderStatus.CANCELED))

    async def trigger_due(self, limit: int = 100) -> None:
        now = self._clock.now()
        for reminder in await self.repository.due(now, limit):
            await self._trigger.trigger(reminder)
            if reminder.recurrence == Recurrence.ONCE:
                updated = replace(reminder, status=ReminderStatus.COMPLETED)
            else:
                days = 1 if reminder.recurrence == Recurrence.DAILY else 7
                local = reminder.due_at.astimezone(ZoneInfo(reminder.timezone))
                while local.astimezone(UTC) <= now:
                    local += timedelta(days=days)
                # For a missing wall time, UTC round-trip moves it forward across the DST gap.
                updated = replace(reminder, due_at=local.astimezone(UTC))
            await self.repository.save(updated)


__all__ = (
    "CalendarEvent",
    "Recurrence",
    "Reminder",
    "ReminderRepository",
    "ReminderService",
    "ReminderStatus",
    "ReminderTrigger",
)
