from app_foundation.notification import NotificationService, NotificationTransport


class SendPendingNotifications:
    name: str = "notification.send_pending"

    def __init__(self, service: NotificationService, transport: NotificationTransport) -> None:
        self._service = service
        self._transport = transport

    async def run(self) -> None:
        await self._service.deliver_pending(self._transport)
