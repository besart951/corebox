from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.identity.models import User
from app_foundation.identity.service import UserNotFound
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import Page, PageRequest, UserId


class UserRecord(Base):
    __tablename__ = "af_users"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    email: Mapped[str] = MappedColumn[str](String(254), unique=True)
    display_name: Mapped[str]
    first_name: Mapped[str]
    last_name: Mapped[str]
    preferred_locale: Mapped[str]
    timezone: Mapped[str]
    active: Mapped[bool]
    created_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    updated_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    profile_metadata: Mapped[list[list[str]]] = MappedColumn[list[list[str]]](JSON)


def _domain(record: UserRecord) -> User:
    return User(
        UserId(record.id),
        record.email,
        record.display_name,
        record.created_at,
        record.updated_at,
        record.first_name,
        record.last_name,
        record.preferred_locale,
        record.timezone,
        record.active,
        tuple((k, v) for k, v in record.profile_metadata),
    )


def _assign(record: UserRecord, user: User) -> None:
    record.email = user.email
    record.display_name = user.display_name
    record.first_name = user.first_name
    record.last_name = user.last_name
    record.preferred_locale = user.preferred_locale
    record.timezone = user.timezone
    record.active = user.active
    record.created_at = user.created_at
    record.updated_at = user.updated_at
    record.profile_metadata = [list(pair) for pair in user.metadata]


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UserId) -> User | None:
        async with translate_errors():
            record = await self._session.get(UserRecord, user_id)
            return _domain(record) if record else None

    async def get_by_email(self, email: str) -> User | None:
        async with translate_errors():
            record = await self._session.scalar(select(UserRecord).where(UserRecord.email == email))
            return _domain(record) if record else None

    async def add(self, user: User) -> None:
        async with translate_errors():
            record = UserRecord(id=user.id)
            _assign(record, user)
            self._session.add(record)
            await self._session.flush()

    async def save(self, user: User) -> None:
        async with translate_errors():
            record = await self._session.get(UserRecord, user.id)
            if record is None:
                raise UserNotFound("User not found")
            _assign(record, user)
            await self._session.flush()

    async def list(self, page: PageRequest) -> Page[User]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(UserRecord).order_by(UserRecord.id).offset(page.offset).limit(page.limit)
            )
            total = await self._session.scalar(select(func.count()).select_from(UserRecord))
            return Page(tuple(_domain(row) for row in rows), total or 0)
