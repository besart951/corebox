from app_foundation.billing import BillingService


class SyncSubscriptions:
    name: str = "billing.sync_subscriptions"

    def __init__(self, service: BillingService) -> None:
        self._service = service

    async def run(self) -> None:
        await self._service.sync_subscriptions()
