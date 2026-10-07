from app_foundation.identity.models import User
from app_foundation.identity.service import EmailAlreadyExists, UserNotFound
from app_foundation.primitives import Page, PageRequest, UserId


class MemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[UserId, User] = {}

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        if user.id in self._users or await self.get_by_email(user.email):
            raise EmailAlreadyExists("Email already exists")
        self._users[user.id] = user

    async def save(self, user: User) -> None:
        if user.id not in self._users:
            raise UserNotFound("User not found")
        self._users[user.id] = user

    async def list(self, page: PageRequest) -> Page[User]:
        users = sorted(self._users.values(), key=lambda user: user.id)
        return Page(tuple(users[page.offset : page.offset + page.limit]), len(users))
