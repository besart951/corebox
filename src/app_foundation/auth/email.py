"""Encrypted transactional queue for short-lived verification links."""

from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid7

from cryptography.fernet import Fernet
from sqlalchemy import DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.communication.email import EmailAddress, EmailMessage, EmailSender
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import Clock, FoundationError


class VerificationDeliveryRecord(Base):
    __tablename__ = "af_verification_deliveries"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    recipient: Mapped[str]
    purpose: Mapped[str]
    encrypted_token: Mapped[str]
    available_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    attempts: Mapped[int]


class QueuedVerificationSender:
    def __init__(self, session: AsyncSession, encryption_key: bytes, clock: Clock) -> None:
        self._session = session
        self._cipher = Fernet(encryption_key)
        self._clock = clock

    async def send(self, email: str, purpose: str, token: str) -> None:
        async with translate_errors():
            self._session.add(
                VerificationDeliveryRecord(
                    id=uuid7(),
                    recipient=email,
                    purpose=purpose,
                    encrypted_token=self._cipher.encrypt(token.encode()).decode(),
                    available_at=self._clock.now(),
                    attempts=0,
                )
            )
            await self._session.flush()

    async def deliver_pending(
        self, sender: EmailSender, from_address: EmailAddress, public_url: str
    ) -> None:
        async with translate_errors():
            rows = await self._session.scalars(
                select(VerificationDeliveryRecord)
                .where(
                    VerificationDeliveryRecord.available_at <= self._clock.now(),
                    VerificationDeliveryRecord.attempts < 5,
                )
                .limit(50)
                .with_for_update(skip_locked=True)
            )
            for row in rows:
                token = self._cipher.decrypt(row.encrypted_token.encode()).decode()
                link = (
                    public_url.rstrip("/") + "/" + row.purpose + "?" + urlencode({"token": token})
                )
                try:
                    await sender.send(
                        EmailMessage(
                            from_address, (EmailAddress(row.recipient),), row.purpose, link
                        )
                    )
                except FoundationError:
                    row.attempts += 1
                    row.available_at = self._clock.now() + timedelta(seconds=30 * 2**row.attempts)
                else:
                    await self._session.delete(row)
