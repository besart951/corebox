from datetime import datetime
from uuid import UUID

from app_foundation.primitives import OrganizationId
from app_foundation.scheduling import CalendarEvent, Reminder, ReminderStatus


class MemoryReminderRepository:
    def __init__(self) -> None:
        self.reminders: dict[UUID, Reminder] = {}
        self.calendar: dict[UUID, CalendarEvent] = {}

    async def save(self, reminder: Reminder) -> None:
        self.reminders[reminder.id] = reminder

    async def get(self, organization_id: OrganizationId, reminder_id: UUID) -> Reminder | None:
        r = self.reminders.get(reminder_id)
        return r if r and r.organization_id == organization_id else None

    async def due(self, now: datetime, limit: int) -> tuple[Reminder, ...]:
        return tuple(
            sorted(
                (
                    r
                    for r in self.reminders.values()
                    if r.status == ReminderStatus.PENDING and r.due_at <= now
                ),
                key=lambda r: r.due_at,
            )
        )[:limit]

    async def save_event(self, event: CalendarEvent) -> None:
        self.calendar[event.id] = event

    async def events(
        self, organization_id: OrganizationId, start: datetime, end: datetime
    ) -> tuple[CalendarEvent, ...]:
        return tuple(
            e
            for e in self.calendar.values()
            if e.organization_id == organization_id and e.starts_at < end and e.ends_at > start
        )
