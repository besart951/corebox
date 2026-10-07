from uuid import UUID, uuid7

from sqlalchemy import JSON, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.access_control import Permission, Role, RoleAssignment
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import OrganizationId, UserId


class RoleRecord(Base):
    __tablename__ = "af_roles"
    name: Mapped[str] = MappedColumn[str](primary_key=True)
    permissions: Mapped[list[str]] = MappedColumn[list[str]](JSON)


class RoleAssignmentRecord(Base):
    __tablename__ = "af_role_assignments"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"), index=True)
    role: Mapped[str] = MappedColumn[str](ForeignKey("af_roles.name"))
    organization_id: Mapped[UUID | None] = MappedColumn[UUID | None](
        ForeignKey("af_organizations.id")
    )


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_role(self, role: Role) -> None:
        async with translate_errors():
            await self._session.merge(
                RoleRecord(name=role.name, permissions=sorted(role.permissions))
            )
            await self._session.flush()

    async def assign(self, assignment: RoleAssignment) -> None:
        async with translate_errors():
            self._session.add(
                RoleAssignmentRecord(
                    id=uuid7(),
                    user_id=assignment.user_id,
                    role=assignment.role,
                    organization_id=assignment.organization_id,
                )
            )
            await self._session.flush()

    async def permissions(
        self, user_id: UserId, organization_id: OrganizationId | None
    ) -> frozenset[Permission]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(RoleRecord)
                .join(RoleAssignmentRecord, RoleRecord.name == RoleAssignmentRecord.role)
                .where(
                    RoleAssignmentRecord.user_id == user_id,
                    RoleAssignmentRecord.organization_id == organization_id,
                )
            )
            return frozenset(p for r in rows for p in r.permissions)
