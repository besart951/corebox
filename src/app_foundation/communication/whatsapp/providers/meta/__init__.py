import httpx
from pydantic import BaseModel, ValidationError

from app_foundation.communication.whatsapp import WhatsAppMessage
from app_foundation.config import WhatsAppSettings
from app_foundation.primitives import InfrastructureUnavailable


class _Message(BaseModel):
    id: str


class _Response(BaseModel):
    messages: list[_Message]


class MetaWhatsAppSender:
    def __init__(self, settings: WhatsAppSettings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def send(self, message: WhatsAppMessage) -> str:
        payload: dict[str, object] = {
            "messaging_product": "whatsapp",
            "to": message.recipient.lstrip("+"),
        }
        if message.template:
            payload.update(
                type="template",
                template={
                    "name": message.template,
                    "language": {"code": message.language},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": p} for p in message.parameters],
                        }
                    ]
                    if message.parameters
                    else [],
                },
            )
        else:
            payload.update(type="text", text={"body": message.text})
        try:
            response = await self._client.post(
                f"https://graph.facebook.com/{self._settings.api_version}/{self._settings.phone_number_id}/messages",
                headers={
                    "Authorization": "Bearer " + self._settings.access_token.get_secret_value()
                },
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            result = _Response.model_validate_json(response.content)
            if not result.messages:
                raise InfrastructureUnavailable("WhatsApp returned no message identifier")
            return result.messages[0].id
        except (httpx.HTTPError, ValidationError) as error:
            raise InfrastructureUnavailable("WhatsApp delivery failed") from error
