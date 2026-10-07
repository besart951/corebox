"""PostgreSQL limiter owns a separate transaction so failed attempts persist."""

from datetime import datetime, timedelta
from hashlib import sha256

from sqlalchemy import DateTime, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.auth.models import RateLimitExceeded
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import Clock


class RateLimitRecord(Base):
    __tablename__ = "af_rate_limits"
    key: Mapped[str] = MappedColumn[str](primary_key=True)
    started_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True), index=True)
    attempts: Mapped[int]


class PostgresRateLimiter:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        limit: int = 10,
        window_seconds: int = 60,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)

    async def require(self, key: str) -> None:
        digest = sha256(key.encode()).hexdigest()
        now = self._clock.now()
        rejected = False
        async with translate_errors(), self._sessions.begin() as session:
            await session.execute(
                insert(RateLimitRecord)
                .values(key=digest, started_at=now, attempts=0)
                .on_conflict_do_nothing()
            )
            row = await session.scalar(
                select(RateLimitRecord).where(RateLimitRecord.key == digest).with_for_update()
            )
            assert row is not None
            if row.started_at + self._window <= now:
                row.started_at = now
                row.attempts = 0
            rejected = row.attempts >= self._limit
            if not rejected:
                row.attempts += 1
        if rejected:
            raise RateLimitExceeded("Too many attempts")

    async def cleanup(self) -> None:
        async with translate_errors(), self._sessions.begin() as session:
            await session.execute(
                delete(RateLimitRecord).where(
                    RateLimitRecord.started_at < self._clock.now() - self._window
                )
            )
