import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app_foundation.persistence import models as _models  # noqa: F401 - register all ORM records
from app_foundation.persistence.migrations.versions import (
    af0001_initial_foundation_schema as initial,
)
from app_foundation.persistence.migrations.versions import (
    af0002_tenant_constraints_and_notification_ as second,
)


def migrate(connection: Connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        initial.upgrade()
        second.upgrade()


@pytest.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    url = os.environ.get("FOUNDATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FOUNDATION_TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = "test_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()
