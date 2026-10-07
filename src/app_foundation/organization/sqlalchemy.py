from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.organization import (
    Invitation,
    Membership,
    MembershipRole,
    MembershipState,
    Organization,
    Team,
)
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import MembershipId, OrganizationId, TeamId, UserId


class OrganizationRecord(Base):
    __tablename__ = "af_organizations"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))


class TeamRecord(Base):
    __tablename__ = "af_teams"
    __table_args__ = (UniqueConstraint("id", "organization_id"),)
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_organizations.id"))
    name: Mapped[str]


class MembershipRecord(Base):
    __tablename__ = "af_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "organization_id"], ["af_teams.id", "af_teams.organization_id"]
        ),
        Index(
            "uq_af_org_member",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("team_id IS NULL"),
            sqlite_where=text("team_id IS NULL"),
        ),
        Index("uq_af_team_member", "organization_id", "user_id", "team_id", unique=True),
    )
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_organizations.id"))
    user_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_users.id"))
    team_id: Mapped[UUID | None] = MappedColumn[UUID | None](ForeignKey("af_teams.id"))
    role: Mapped[str]
    state: Mapped[str]


class InvitationRecord(Base):
    __tablename__ = "af_invitations"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_organizations.id"))
    email: Mapped[str]
    role: Mapped[str]
    token_digest: Mapped[str] = MappedColumn[str](unique=True)
    expires_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = MappedColumn[datetime | None](DateTime(timezone=True))


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_organization(self, organization: Organization) -> None:
        async with translate_errors():
            self._session.add(
                OrganizationRecord(
                    id=organization.id, name=organization.name, created_at=organization.created_at
                )
            )
            await self._session.flush()

    async def get_organization(self, organization_id: OrganizationId) -> Organization | None:
        async with translate_errors():
            row = await self._session.get(OrganizationRecord, organization_id)
            return Organization(OrganizationId(row.id), row.name, row.created_at) if row else None

    async def add_team(self, team: Team) -> None:
        async with translate_errors():
            self._session.add(
                TeamRecord(id=team.id, name=team.name, organization_id=team.organization_id)
            )
            await self._session.flush()

    async def get_team(self, organization_id: OrganizationId, team_id: TeamId) -> Team | None:
        async with translate_errors():
            row = await self._session.scalar(
                select(TeamRecord).where(
                    TeamRecord.id == team_id, TeamRecord.organization_id == organization_id
                )
            )
            return (
                Team(TeamId(row.id), OrganizationId(row.organization_id), row.name) if row else None
            )

    async def save_membership(self, membership: Membership) -> None:
        async with translate_errors():
            await self._session.merge(
                MembershipRecord(
                    id=membership.id,
                    organization_id=membership.organization_id,
                    user_id=membership.user_id,
                    team_id=membership.team_id,
                    role=membership.role.value,
                    state=membership.state.value,
                )
            )
            await self._session.flush()

    async def memberships(
        self, organization_id: OrganizationId, user_id: UserId
    ) -> tuple[Membership, ...]:
        async with translate_errors():
            rows = await self._session.scalars(
                select(MembershipRecord).where(
                    MembershipRecord.organization_id == organization_id,
                    MembershipRecord.user_id == user_id,
                )
            )
            return tuple(
                Membership(
                    MembershipId(r.id),
                    OrganizationId(r.organization_id),
                    UserId(r.user_id),
                    MembershipRole(r.role),
                    MembershipState(r.state),
                    TeamId(r.team_id) if r.team_id else None,
                )
                for r in rows
            )

    async def save_invitation(self, invitation: Invitation) -> None:
        async with translate_errors():
            await self._session.merge(
                InvitationRecord(
                    id=invitation.id,
                    organization_id=invitation.organization_id,
                    email=invitation.email,
                    role=invitation.role.value,
                    token_digest=invitation.token_digest,
                    expires_at=invitation.expires_at,
                    accepted_at=invitation.accepted_at,
                )
            )
            await self._session.flush()

    async def invitation_for_update(self, digest: str) -> Invitation | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(InvitationRecord)
                .where(InvitationRecord.token_digest == digest)
                .with_for_update()
            )
            return (
                Invitation(
                    r.id,
                    OrganizationId(r.organization_id),
                    r.email,
                    MembershipRole(r.role),
                    r.token_digest,
                    r.expires_at,
                    r.accepted_at,
                )
                if r
                else None
            )
