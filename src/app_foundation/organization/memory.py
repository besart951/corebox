from uuid import UUID

from app_foundation.organization import Invitation, Membership, Organization, Team
from app_foundation.primitives import MembershipId, OrganizationId, TeamId, UserId


class MemoryOrganizationRepository:
    def __init__(self) -> None:
        self.organizations: dict[OrganizationId, Organization] = {}
        self.teams: dict[TeamId, Team] = {}
        self.members: dict[MembershipId, Membership] = {}
        self.invitations: dict[UUID, Invitation] = {}

    async def add_organization(self, organization: Organization) -> None:
        self.organizations[organization.id] = organization

    async def get_organization(self, organization_id: OrganizationId) -> Organization | None:
        return self.organizations.get(organization_id)

    async def add_team(self, team: Team) -> None:
        self.teams[team.id] = team

    async def get_team(self, organization_id: OrganizationId, team_id: TeamId) -> Team | None:
        team = self.teams.get(team_id)
        return team if team and team.organization_id == organization_id else None

    async def save_membership(self, membership: Membership) -> None:
        self.members[membership.id] = membership

    async def memberships(
        self, organization_id: OrganizationId, user_id: UserId
    ) -> tuple[Membership, ...]:
        return tuple(
            m
            for m in self.members.values()
            if m.organization_id == organization_id and m.user_id == user_id
        )

    async def save_invitation(self, invitation: Invitation) -> None:
        self.invitations[invitation.id] = invitation

    async def invitation_for_update(self, digest: str) -> Invitation | None:
        return next((i for i in self.invitations.values() if i.token_digest == digest), None)
