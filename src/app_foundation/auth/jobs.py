from app_foundation.auth.protocols import SessionRepository
from app_foundation.primitives import Clock


class DeleteExpiredSessions:
    name: str = "auth.delete_expired_sessions"

    def __init__(self, repository: SessionRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def run(self) -> None:
        await self._repository.delete_expired_sessions(self._clock.now())
