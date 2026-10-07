from dataclasses import dataclass
from typing import Protocol

from app_foundation.organization import MembershipState, OrganizationRepository
from app_foundation.primitives import OrganizationId, PermissionDenied, UserId

type Permission = str


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UserId


@dataclass(frozen=True, slots=True)
class Resource:
    organization_id: OrganizationId | None = None
    owner_id: UserId | None = None


@dataclass(frozen=True, slots=True)
class Role:
    name: str
    permissions: frozenset[Permission]


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    user_id: UserId
    role: str
    organization_id: OrganizationId | None


class RoleRepository(Protocol):
    async def save_role(self, role: Role) -> None: ...
    async def assign(self, assignment: RoleAssignment) -> None: ...
    async def permissions(
        self, user_id: UserId, organization_id: OrganizationId | None
    ) -> frozenset[Permission]: ...


class Policy(Protocol):
    async def allows(
        self, principal: Principal, permission: Permission, resource: Resource
    ) -> bool: ...


class Authorizer:
    def __init__(
        self,
        roles: RoleRepository,
        organizations: OrganizationRepository,
        policies: tuple[Policy, ...] = (),
    ) -> None:
        self._roles = roles
        self._organizations = organizations
        self._policies = policies

    async def allows(
        self, principal: Principal, permission: Permission, resource: Resource
    ) -> bool:
        if resource.organization_id:
            memberships = await self._organizations.memberships(
                resource.organization_id, principal.user_id
            )
            if not any(
                m.team_id is None and m.state == MembershipState.ACTIVE for m in memberships
            ):
                return False
        permissions = await self._roles.permissions(principal.user_id, resource.organization_id)
        if permission in permissions:
            return True
        return any(
            [await policy.allows(principal, permission, resource) for policy in self._policies]
        )

    async def require(
        self, principal: Principal, permission: Permission, resource: Resource
    ) -> None:
        if not await self.allows(principal, permission, resource):
            raise PermissionDenied("Permission denied")


class OwnerPolicy:
    def __init__(self, permissions: frozenset[Permission]) -> None:
        self._permissions = permissions

    async def allows(
        self, principal: Principal, permission: Permission, resource: Resource
    ) -> bool:
        return resource.owner_id == principal.user_id and permission in self._permissions


__all__ = (
    "Authorizer",
    "OwnerPolicy",
    "Permission",
    "Policy",
    "Principal",
    "Resource",
    "Role",
    "RoleAssignment",
    "RoleRepository",
)
