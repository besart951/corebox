import re
from dataclasses import dataclass
from typing import Protocol

from app_foundation.primitives import ValidationError


@dataclass(frozen=True, slots=True)
class WhatsAppMessage:
    recipient: str
    text: str = ""
    template: str | None = None
    language: str = "en"
    parameters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\+[1-9]\d{7,14}", self.recipient):
            raise ValidationError("Recipient must be an E.164 number")
        if not self.text and not self.template:
            raise ValidationError("Text or template is required")
        if self.text and self.template:
            raise ValidationError("Select text or a template")


class WhatsAppSender(Protocol):
    async def send(self, message: WhatsAppMessage) -> str: ...


class MemoryWhatsAppSender:
    def __init__(self) -> None:
        self.messages: list[WhatsAppMessage] = []

    async def send(self, message: WhatsAppMessage) -> str:
        self.messages.append(message)
        return str(len(self.messages))


__all__ = ("MemoryWhatsAppSender", "WhatsAppMessage", "WhatsAppSender")
