from app_foundation.access_control import Permission, Role, RoleAssignment
from app_foundation.primitives import OrganizationId, UserId


class MemoryRoleRepository:
    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._assignments: set[RoleAssignment] = set()

    async def save_role(self, role: Role) -> None:
        self._roles[role.name] = role

    async def assign(self, assignment: RoleAssignment) -> None:
        self._assignments.add(assignment)

    async def permissions(
        self, user_id: UserId, organization_id: OrganizationId | None
    ) -> frozenset[Permission]:
        return frozenset(
            p
            for a in self._assignments
            if a.user_id == user_id and a.organization_id == organization_id
            for p in self._roles[a.role].permissions
        )
