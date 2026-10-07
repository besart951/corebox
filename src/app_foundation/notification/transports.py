from app_foundation.communication.email import EmailAddress, EmailMessage, EmailSender
from app_foundation.communication.whatsapp import WhatsAppMessage, WhatsAppSender
from app_foundation.notification import Delivery, NotificationChannel
from app_foundation.primitives import InfrastructureUnavailable


class CommunicationTransport:
    def __init__(
        self,
        sender_address: EmailAddress,
        email: EmailSender,
        whatsapp: WhatsAppSender | None = None,
    ) -> None:
        self._sender = sender_address
        self._email = email
        self._whatsapp = whatsapp

    async def deliver(self, delivery: Delivery) -> None:
        match delivery.channel:
            case NotificationChannel.EMAIL:
                await self._email.send(
                    EmailMessage(
                        self._sender,
                        (EmailAddress(delivery.recipient),),
                        delivery.title,
                        delivery.body,
                    )
                )
            case NotificationChannel.WHATSAPP:
                if self._whatsapp is None:
                    raise InfrastructureUnavailable("WhatsApp transport is not configured")
                await self._whatsapp.send(WhatsAppMessage(delivery.recipient, delivery.body))
            case NotificationChannel.IN_APP:
                raise InfrastructureUnavailable("In-app messages do not use a transport")
