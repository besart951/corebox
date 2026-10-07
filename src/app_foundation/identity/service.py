from dataclasses import replace

from app_foundation.events import ApplicationEvent, EventPublisher
from app_foundation.identity.models import User, normalize_email
from app_foundation.identity.protocols import UserRepository
from app_foundation.primitives import Clock, Conflict, IdGenerator, Metadata, NotFound, UserId


class UserNotFound(NotFound):
    pass


class EmailAlreadyExists(Conflict):
    pass


class UserService:
    def __init__(
        self, repository: UserRepository, clock: Clock, ids: IdGenerator, events: EventPublisher
    ) -> None:
        self.repository = repository
        self._clock = clock
        self._ids = ids
        self._events = events

    async def create(self, email: str, display_name: str) -> User:
        normalized = normalize_email(email)
        if await self.repository.get_by_email(normalized):
            raise EmailAlreadyExists("Email already exists")
        now = self._clock.now()
        user = User(UserId(self._ids.new()), normalized, display_name, now, now)
        try:
            await self.repository.add(user)
        except Conflict as error:
            raise EmailAlreadyExists("Email already exists") from error
        await self._events.publish((ApplicationEvent("user.created", user.id, now),))
        return user

    async def get(self, user_id: UserId) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound("User not found")
        return user

    async def update_profile(
        self,
        user_id: UserId,
        *,
        display_name: str,
        first_name: str = "",
        last_name: str = "",
        preferred_locale: str = "en",
        timezone: str = "UTC",
        metadata: Metadata = (),
    ) -> User:
        user = replace(
            await self.get(user_id),
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            preferred_locale=preferred_locale,
            timezone=timezone,
            metadata=metadata,
            updated_at=self._clock.now(),
        )
        await self.repository.save(user)
        await self._events.publish((ApplicationEvent("user.updated", user.id, user.updated_at),))
        return user

    async def deactivate(self, user_id: UserId) -> User:
        user = replace(await self.get(user_id), active=False, updated_at=self._clock.now())
        await self.repository.save(user)
        await self._events.publish(
            (ApplicationEvent("user.deactivated", user.id, user.updated_at),)
        )
        return user
