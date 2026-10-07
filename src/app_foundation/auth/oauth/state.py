from datetime import datetime

from sqlalchemy import DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.auth.service import token_digest
from app_foundation.persistence import Base, translate_errors


class OAuthStateRecord(Base):
    __tablename__ = "af_oauth_states"
    digest: Mapped[str] = MappedColumn[str](primary_key=True)
    encrypted_data: Mapped[str]
    expires_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    consumed: Mapped[bool]


class SqlAlchemyOAuthStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, state: str, encrypted_data: str, expires_at: datetime) -> None:
        async with translate_errors():
            self._session.add(
                OAuthStateRecord(
                    digest=token_digest(state),
                    encrypted_data=encrypted_data,
                    expires_at=expires_at,
                    consumed=False,
                )
            )
            await self._session.flush()

    async def consume(self, state: str, now: datetime) -> str | None:
        async with translate_errors():
            row = await self._session.scalar(
                select(OAuthStateRecord)
                .where(OAuthStateRecord.digest == token_digest(state))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None or row.consumed or row.expires_at <= now:
                return None
            row.consumed = True
            await self._session.flush()
            return row.encrypted_data


class MemoryOAuthStateRepository:
    def __init__(self) -> None:
        self._states: dict[str, tuple[str, datetime]] = {}

    async def save(self, state: str, encrypted_data: str, expires_at: datetime) -> None:
        self._states[token_digest(state)] = encrypted_data, expires_at

    async def consume(self, state: str, now: datetime) -> str | None:
        data = self._states.pop(token_digest(state), None)
        return data[0] if data and data[1] > now else None
