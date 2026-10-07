from dataclasses import dataclass
from typing import Protocol

from app_foundation.identity import normalize_email
from app_foundation.primitives import Metadata, ValidationError


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", normalize_email(self.value))


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if (
            any(c in self.filename + self.content_type for c in "\r\n")
            or "/" not in self.content_type
        ):
            raise ValidationError("Invalid attachment headers")


@dataclass(frozen=True, slots=True)
class EmailMessage:
    sender: EmailAddress
    to: tuple[EmailAddress, ...]
    subject: str
    text: str = ""
    html: str | None = None
    cc: tuple[EmailAddress, ...] = ()
    bcc: tuple[EmailAddress, ...] = ()
    reply_to: EmailAddress | None = None
    attachments: tuple[EmailAttachment, ...] = ()
    metadata: Metadata = ()

    def __post_init__(self) -> None:
        if not self.to or any(c in self.subject for c in "\r\n"):
            raise ValidationError("Recipients and a safe subject are required")


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class MemoryEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


__all__ = ("EmailAddress", "EmailAttachment", "EmailMessage", "EmailSender", "MemoryEmailSender")
