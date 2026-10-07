import asyncio
import os

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app_foundation.persistence import Base, migration_location
from app_foundation.persistence import models as _models  # noqa: F401 - register tables

config = context.config
config.set_main_option("version_locations", str(migration_location()))
url = os.environ["FOUNDATION_DATABASE_URL"]


def configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
