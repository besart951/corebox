from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID

from app_foundation.events import ApplicationEvent, EventPublisher
from app_foundation.identity import normalize_email
from app_foundation.primitives import (
    Clock,
    Conflict,
    IdGenerator,
    MembershipId,
    NotFound,
    OrganizationId,
    TeamId,
    UserId,
    ValidationError,
)


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MembershipState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class Organization:
    id: OrganizationId
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Team:
    id: TeamId
    organization_id: OrganizationId
    name: str


@dataclass(frozen=True, slots=True)
class Membership:
    id: MembershipId
    organization_id: OrganizationId
    user_id: UserId
    role: MembershipRole
    state: MembershipState = MembershipState.ACTIVE
    team_id: TeamId | None = None


@dataclass(frozen=True, slots=True)
class Invitation:
    id: UUID
    organization_id: OrganizationId
    email: str
    role: MembershipRole
    token_digest: str
    expires_at: datetime
    accepted_at: datetime | None = None


class OrganizationRepository(Protocol):
    async def add_organization(self, organization: Organization) -> None: ...
    async def get_organization(self, organization_id: OrganizationId) -> Organization | None: ...
    async def add_team(self, team: Team) -> None: ...
    async def get_team(self, organization_id: OrganizationId, team_id: TeamId) -> Team | None: ...
    async def save_membership(self, membership: Membership) -> None: ...
    async def memberships(
        self, organization_id: OrganizationId, user_id: UserId
    ) -> tuple[Membership, ...]: ...
    async def save_invitation(self, invitation: Invitation) -> None: ...
    async def invitation_for_update(self, digest: str) -> Invitation | None: ...


class OrganizationService:
    def __init__(
        self,
        repository: OrganizationRepository,
        clock: Clock,
        ids: IdGenerator,
        events: EventPublisher,
    ) -> None:
        self.repository = repository
        self._clock = clock
        self._ids = ids
        self._events = events

    async def create(self, name: str, owner: UserId) -> Organization:
        if not name.strip():
            raise ValidationError("Organization name is required")
        organization = Organization(
            OrganizationId(self._ids.new()), name.strip(), self._clock.now()
        )
        await self.repository.add_organization(organization)
        await self.add_member(organization.id, owner, MembershipRole.OWNER)
        return organization

    async def create_team(self, organization_id: OrganizationId, name: str) -> Team:
        if not await self.repository.get_organization(organization_id):
            raise NotFound("Organization not found")
        if not name.strip():
            raise ValidationError("Team name is required")
        team = Team(TeamId(self._ids.new()), organization_id, name.strip())
        await self.repository.add_team(team)
        return team

    async def add_member(
        self,
        organization_id: OrganizationId,
        user_id: UserId,
        role: MembershipRole,
        team_id: TeamId | None = None,
    ) -> Membership:
        if not await self.repository.get_organization(organization_id):
            raise NotFound("Organization not found")
        if team_id and not await self.repository.get_team(organization_id, team_id):
            raise NotFound("Team not found in organization")
        existing = await self.repository.memberships(organization_id, user_id)
        if any(item.team_id == team_id for item in existing):
            raise Conflict("Membership already exists")
        if team_id and not any(
            item.team_id is None and item.state == MembershipState.ACTIVE for item in existing
        ):
            raise ValidationError("Team members must belong to the organization")
        membership = Membership(
            MembershipId(self._ids.new()), organization_id, user_id, role, team_id=team_id
        )
        await self.repository.save_membership(membership)
        await self._events.publish(
            (ApplicationEvent("membership.added", membership.id, self._clock.now()),)
        )
        return membership

    async def set_membership_state(
        self,
        organization_id: OrganizationId,
        user_id: UserId,
        state: MembershipState,
        team_id: TeamId | None = None,
    ) -> Membership:
        memberships = await self.repository.memberships(organization_id, user_id)
        membership = next((m for m in memberships if m.team_id == team_id), None)
        if membership is None:
            raise NotFound("Membership not found")
        if membership.role == MembershipRole.OWNER and state == MembershipState.SUSPENDED:
            raise Conflict("Owner memberships cannot be suspended")
        updated = replace(membership, state=state)
        await self.repository.save_membership(updated)
        await self._events.publish(
            (ApplicationEvent("membership.updated", updated.id, self._clock.now()),)
        )
        return updated

    async def invite(
        self, organization_id: OrganizationId, email: str, role: MembershipRole
    ) -> tuple[Invitation, str]:
        if not await self.repository.get_organization(organization_id):
            raise NotFound("Organization not found")
        raw = token_urlsafe(32)
        invitation = Invitation(
            self._ids.new(),
            organization_id,
            normalize_email(email),
            role,
            sha256(raw.encode()).hexdigest(),
            self._clock.now() + timedelta(days=7),
        )
        await self.repository.save_invitation(invitation)
        return invitation, raw

    async def accept_invitation(
        self, token: str, user_id: UserId, verified_email: str
    ) -> Membership:
        invitation = await self.repository.invitation_for_update(sha256(token.encode()).hexdigest())
        if (
            invitation is None
            or invitation.accepted_at
            or invitation.expires_at <= self._clock.now()
        ):
            raise ValidationError("Invitation is invalid or expired")
        if invitation.email != normalize_email(verified_email):
            raise ValidationError("Invitation belongs to another email")
        member = await self.add_member(invitation.organization_id, user_id, invitation.role)
        await self.repository.save_invitation(replace(invitation, accepted_at=self._clock.now()))
        return member


__all__ = (
    "Invitation",
    "Membership",
    "MembershipId",
    "MembershipRole",
    "MembershipState",
    "Organization",
    "OrganizationId",
    "OrganizationRepository",
    "OrganizationService",
    "Team",
    "TeamId",
)
