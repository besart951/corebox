from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app_foundation.persistence import translate_errors


class PostgresLock:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def acquire(self, name: str) -> AsyncIterator[bool]:
        key = int.from_bytes(sha256(name.encode()).digest()[:8], signed=True)
        async with translate_errors(), self._engine.begin() as connection:
            result = await connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
            )
            yield result.scalar_one() is True
