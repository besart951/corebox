"""SQLAlchemy infrastructure; feature roots never import this package."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

from sqlalchemy import MetaData
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app_foundation.events import Event, EventPublisher
from app_foundation.primitives import Conflict, InfrastructureUnavailable


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def create_database(url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def migration_location() -> Path:
    return Path(str(files("app_foundation.persistence.migrations").joinpath("versions")))


class Transaction:
    """One operation owns this context; repositories only flush."""

    def __init__(self, session: AsyncSession, publisher: EventPublisher) -> None:
        self.session = session
        self._publisher = publisher
        self._events: list[Event] = []

    async def publish(self, events: tuple[Event, ...]) -> None:
        self._events.extend(events)

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[Transaction]:
        try:
            async with self.session.begin():
                yield self
        except IntegrityError as error:
            self._events.clear()
            raise Conflict("A persistence constraint was violated") from error
        except SQLAlchemyError as error:
            self._events.clear()
            raise InfrastructureUnavailable("Database operation failed") from error
        except BaseException:
            self._events.clear()
            raise
        events = tuple(self._events)
        self._events.clear()
        await self._publisher.publish(events)


@asynccontextmanager
async def translate_errors() -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as error:
        raise Conflict("A persistence constraint was violated") from error
    except SQLAlchemyError as error:
        raise InfrastructureUnavailable("Database operation failed") from error


__all__ = ("Base", "Transaction", "create_database", "migration_location")
