from app_foundation.scheduling import ReminderService


class TriggerReminders:
    name: str = "scheduling.trigger_reminders"

    def __init__(self, service: ReminderService) -> None:
        self._service = service

    async def run(self) -> None:
        await self._service.trigger_due()
