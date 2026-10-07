from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.auth.models import (
    Credential,
    MfaEnrollment,
    RefreshToken,
    Session,
    TokenPurpose,
    VerificationToken,
)
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import UserId


class CredentialRecord(Base):
    __tablename__ = "af_credentials"
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), primary_key=True)
    password_hash: Mapped[str]
    email_verified: Mapped[bool]


class SessionRecord(Base):
    __tablename__ = "af_sessions"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), index=True)
    expires_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True), index=True)
    revoked: Mapped[bool]


class RefreshRecord(Base):
    __tablename__ = "af_refresh_tokens"
    digest: Mapped[str] = MappedColumn[str](primary_key=True)
    session_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_sessions.id", ondelete="CASCADE"), index=True
    )
    consumed: Mapped[bool]


class VerificationRecord(Base):
    __tablename__ = "af_verification_tokens"
    digest: Mapped[str] = MappedColumn[str](primary_key=True)
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"))
    purpose: Mapped[str]
    expires_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    consumed: Mapped[bool]
    data: Mapped[str]


class MfaRecord(Base):
    __tablename__ = "af_mfa"
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), primary_key=True)
    encrypted_secret: Mapped[str]
    confirmed: Mapped[bool]
    recovery_digests: Mapped[list[str]] = MappedColumn[list[str]](JSON)
    last_counter: Mapped[int]


class OAuthIdentityRecord(Base):
    __tablename__ = "af_oauth_identities"
    provider: Mapped[str] = MappedColumn[str](primary_key=True)
    subject: Mapped[str] = MappedColumn[str](primary_key=True)
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"))


def _purpose(value: str) -> TokenPurpose:
    match value:
        case "verify-email" | "reset-password" | "mfa-login" | "oauth-state":
            return value
        case _:
            raise ValueError("Unknown persisted token purpose")


class SqlAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_credential(self, user_id: UserId) -> Credential | None:
        async with translate_errors():
            row = await self._session.get(CredentialRecord, user_id)
            return (
                Credential(UserId(row.user_id), row.password_hash, row.email_verified)
                if row
                else None
            )

    async def save_credential(self, credential: Credential) -> None:
        async with translate_errors():
            await self._session.merge(
                CredentialRecord(
                    user_id=credential.user_id,
                    password_hash=credential.password_hash,
                    email_verified=credential.email_verified,
                )
            )
            await self._session.flush()

    async def save_session(self, session: Session) -> None:
        async with translate_errors():
            await self._session.merge(
                SessionRecord(
                    id=session.id,
                    user_id=session.user_id,
                    expires_at=session.expires_at,
                    revoked=session.revoked,
                )
            )
            await self._session.flush()

    async def get_session(self, session_id: UUID) -> Session | None:
        async with translate_errors():
            row = await self._session.get(SessionRecord, session_id)
            return (
                Session(row.id, UserId(row.user_id), row.expires_at, row.revoked) if row else None
            )

    async def save_refresh(self, token: RefreshToken) -> None:
        async with translate_errors():
            await self._session.merge(
                RefreshRecord(
                    digest=token.digest, session_id=token.session_id, consumed=token.consumed
                )
            )
            await self._session.flush()

    async def refresh_for_update(self, digest: str) -> tuple[RefreshToken, Session] | None:
        async with translate_errors():
            # Lock the entire family first; different token generations serialize on this row.
            row = await self._session.scalar(
                select(SessionRecord)
                .join(RefreshRecord)
                .where(RefreshRecord.digest == digest)
                .with_for_update(of=SessionRecord)
                .execution_options(populate_existing=True)
            )
            if row is None:
                return None
            token = await self._session.scalar(
                select(RefreshRecord)
                .where(RefreshRecord.digest == digest)
                .execution_options(populate_existing=True)
            )
            if token is None:
                return None
            return RefreshToken(token.digest, token.session_id, token.consumed), Session(
                row.id, UserId(row.user_id), row.expires_at, row.revoked
            )

    async def revoke_user_sessions(self, user_id: UserId) -> None:
        async with translate_errors():
            await self._session.execute(
                update(SessionRecord).where(SessionRecord.user_id == user_id).values(revoked=True)
            )

    async def delete_expired_sessions(self, now: datetime) -> None:
        async with translate_errors():
            await self._session.execute(
                delete(RefreshRecord).where(
                    RefreshRecord.session_id.in_(
                        select(SessionRecord.id).where(SessionRecord.expires_at <= now)
                    )
                )
            )
            await self._session.execute(
                delete(SessionRecord).where(SessionRecord.expires_at <= now)
            )
            await self._session.execute(
                delete(VerificationRecord).where(VerificationRecord.expires_at <= now)
            )

    async def invalidate_verifications(self, user_id: UserId) -> None:
        async with translate_errors():
            await self._session.execute(
                update(VerificationRecord)
                .where(VerificationRecord.user_id == user_id)
                .values(consumed=True)
            )

    async def save_verification(self, token: VerificationToken) -> None:
        async with translate_errors():
            await self._session.merge(
                VerificationRecord(
                    digest=token.digest,
                    user_id=token.user_id,
                    purpose=token.purpose,
                    expires_at=token.expires_at,
                    consumed=token.consumed,
                    data=token.data,
                )
            )
            await self._session.flush()

    async def verification_for_update(self, digest: str) -> VerificationToken | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(VerificationRecord)
                .where(VerificationRecord.digest == digest)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            return (
                VerificationToken(
                    r.digest,
                    UserId(r.user_id),
                    _purpose(r.purpose),
                    r.expires_at,
                    r.consumed,
                    r.data,
                )
                if r
                else None
            )

    async def mfa_for_update(self, user_id: UserId) -> MfaEnrollment | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(MfaRecord)
                .where(MfaRecord.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            return (
                MfaEnrollment(
                    UserId(r.user_id),
                    r.encrypted_secret,
                    r.confirmed,
                    tuple(r.recovery_digests),
                    r.last_counter,
                )
                if r
                else None
            )

    async def save_mfa(self, enrollment: MfaEnrollment) -> None:
        async with translate_errors():
            await self._session.merge(
                MfaRecord(
                    user_id=enrollment.user_id,
                    encrypted_secret=enrollment.encrypted_secret,
                    confirmed=enrollment.confirmed,
                    recovery_digests=list(enrollment.recovery_digests),
                    last_counter=enrollment.last_counter,
                )
            )
            await self._session.flush()

    async def delete_mfa(self, user_id: UserId) -> None:
        async with translate_errors():
            await self._session.execute(delete(MfaRecord).where(MfaRecord.user_id == user_id))

    async def oauth_user(self, provider: str, subject: str) -> UserId | None:
        async with translate_errors():
            r = await self._session.get(OAuthIdentityRecord, (provider, subject))
            return UserId(r.user_id) if r else None

    async def link_oauth(self, provider: str, subject: str, user_id: UserId) -> None:
        async with translate_errors():
            self._session.add(
                OAuthIdentityRecord(provider=provider, subject=subject, user_id=user_id)
            )
            await self._session.flush()
