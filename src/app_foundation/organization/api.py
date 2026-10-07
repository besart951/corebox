from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field, SecretStr

from app_foundation.access_control import Resource, RoleAssignment, RoleRepository
from app_foundation.api import Authenticate, Authorize, Scope
from app_foundation.identity import UserService
from app_foundation.organization import (
    Membership,
    MembershipRole,
    MembershipState,
    Organization,
    OrganizationService,
    Team,
)
from app_foundation.primitives import NotFound, OrganizationId, TeamId, UserId


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MembershipRequest(BaseModel):
    user_id: UUID
    role: MembershipRole = MembershipRole.MEMBER


class InvitationRequest(BaseModel):
    email: str = Field(max_length=254)
    role: MembershipRole = MembershipRole.MEMBER


class InvitationAcceptanceRequest(BaseModel):
    token: SecretStr = Field(max_length=256)


class MembershipStateRequest(BaseModel):
    state: MembershipState


def create_organization_router(
    scope: Scope[tuple[OrganizationService, RoleRepository]],
    authenticate: Authenticate,
    authorize: Authorize,
    users: Scope[UserService],
) -> APIRouter:
    router = APIRouter(prefix="/organizations", tags=["organizations"])

    @router.post("", status_code=201)
    async def create(body: NameRequest, authorization: str = Header(default="")) -> Organization:
        principal = await authenticate(authorization)
        async with scope() as (service, roles):
            organization = await service.create(body.name, principal.user_id)
            await roles.assign(RoleAssignment(principal.user_id, "owner", organization.id))
            return organization

    @router.post("/{organization_id}/members", status_code=201)
    async def member(
        organization_id: UUID, body: MembershipRequest, authorization: str = Header(default="")
    ) -> Membership:
        org = OrganizationId(organization_id)
        await authorize(authorization, "membership.manage", Resource(org))
        async with scope() as (service, roles):
            membership = await service.add_member(org, UserId(body.user_id), body.role)
            await roles.assign(RoleAssignment(membership.user_id, body.role.value, org))
            return membership

    @router.post("/{organization_id}/invitations", status_code=201)
    async def invite(
        organization_id: UUID, body: InvitationRequest, authorization: str = Header(default="")
    ) -> dict[str, str]:
        org = OrganizationId(organization_id)
        await authorize(authorization, "membership.manage", Resource(org))
        async with scope() as (service, _):
            invitation, token = await service.invite(org, body.email, body.role)
            return {"id": str(invitation.id), "token": token}

    @router.get("/{organization_id}")
    async def get(organization_id: UUID, authorization: str = Header(default="")) -> Organization:
        org = OrganizationId(organization_id)
        await authorize(authorization, "team.read", Resource(org))
        async with scope() as (service, _):
            organization = await service.repository.get_organization(org)
            if organization is None:
                raise NotFound("Organization not found")
            return organization

    @router.post("/invitations/accept")
    async def accept(
        body: InvitationAcceptanceRequest, authorization: str = Header(default="")
    ) -> Membership:
        principal = await authenticate(authorization)
        async with users() as user_service:
            user = await user_service.get(principal.user_id)
        async with scope() as (service, roles):
            membership = await service.accept_invitation(
                body.token.get_secret_value(), user.id, user.email
            )
            await roles.assign(
                RoleAssignment(user.id, membership.role.value, membership.organization_id)
            )
            return membership

    @router.put("/{organization_id}/members/{user_id}/state")
    async def state(
        organization_id: UUID,
        user_id: UUID,
        body: MembershipStateRequest,
        authorization: str = Header(default=""),
    ) -> Membership:
        org = OrganizationId(organization_id)
        await authorize(authorization, "membership.manage", Resource(org))
        async with scope() as (service, _):
            return await service.set_membership_state(org, UserId(user_id), body.state)

    return router


def create_team_router(
    scope: Scope[tuple[OrganizationService, RoleRepository]], authorize: Authorize
) -> APIRouter:
    router = APIRouter(prefix="/organizations/{organization_id}/teams", tags=["teams"])

    @router.post("", status_code=201)
    async def create(
        organization_id: UUID, body: NameRequest, authorization: str = Header(default="")
    ) -> Team:
        org = OrganizationId(organization_id)
        await authorize(authorization, "team.write", Resource(org))
        async with scope() as (service, _):
            return await service.create_team(org, body.name)

    @router.get("/{team_id}")
    async def get(
        organization_id: UUID, team_id: UUID, authorization: str = Header(default="")
    ) -> Team:
        org = OrganizationId(organization_id)
        await authorize(authorization, "team.read", Resource(org))
        async with scope() as (service, _):
            team = await service.repository.get_team(org, TeamId(team_id))
            if team is None:
                raise NotFound("Team not found")
            return team

    @router.post("/{team_id}/members", status_code=201)
    async def add_member(
        organization_id: UUID,
        team_id: UUID,
        body: MembershipRequest,
        authorization: str = Header(default=""),
    ) -> Membership:
        org = OrganizationId(organization_id)
        await authorize(authorization, "membership.manage", Resource(org))
        async with scope() as (service, _):
            return await service.add_member(org, UserId(body.user_id), body.role, TeamId(team_id))

    return router
