from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.observability import AuditRecord
from app_foundation.persistence import Base, translate_errors


class AuditRecordRow(Base):
    __tablename__ = "af_audit_records"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    action: Mapped[str]
    occurred_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    actor_id: Mapped[UUID | None]
    organization_id: Mapped[UUID | None]
    entity_id: Mapped[UUID]
    context: Mapped[list[list[str]]] = MappedColumn[list[list[str]]](JSON)


class SqlAlchemyAuditSink:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, record: AuditRecord) -> None:
        async with translate_errors():
            self._session.add(
                AuditRecordRow(
                    id=record.id,
                    action=record.action,
                    occurred_at=record.occurred_at,
                    actor_id=record.actor_id,
                    organization_id=record.organization_id,
                    entity_id=record.entity_id,
                    context=[list(p) for p in record.metadata],
                )
            )
            await self._session.flush()
