import asyncio
from collections import deque
from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher as ArgonHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel, ConfigDict, ValidationError

from app_foundation.auth.models import AccessClaims, InvalidCredentials, RateLimitExceeded
from app_foundation.config import JwtSettings
from app_foundation.primitives import Clock, UserId


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = ArgonHasher()

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password: str, digest: str) -> bool:
        try:
            return await asyncio.to_thread(self._hasher.verify, digest, password)
        except VerificationError, InvalidHashError:
            return False


class _Claims(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub: UUID
    sid: UUID
    exp: int
    iat: int
    nbf: int
    token_use: str


class JwtTokenIssuer:
    def __init__(self, settings: JwtSettings, clock: Clock) -> None:
        self._settings = settings
        self._clock = clock

    @property
    def access_seconds(self) -> int:
        return self._settings.access_seconds

    def issue(self, user_id: UserId, session_id: UUID) -> str:
        now = self._clock.now()
        return jwt.encode(
            {
                "sub": str(user_id),
                "sid": str(session_id),
                "iss": self._settings.issuer,
                "aud": self._settings.audience,
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(seconds=self.access_seconds),
                "token_use": "access",
            },
            self._settings.secret.get_secret_value(),
            algorithm="HS256",
        )

    def validate(self, token: str) -> AccessClaims:
        try:
            claims = _Claims.model_validate(
                jwt.decode(
                    token,
                    self._settings.secret.get_secret_value(),
                    algorithms=["HS256"],
                    issuer=self._settings.issuer,
                    audience=self._settings.audience,
                    options={
                        "require": ["sub", "sid", "exp", "iat", "nbf", "iss", "aud", "token_use"],
                        "verify_exp": False,
                        "verify_iat": False,
                        "verify_nbf": False,
                    },
                )
            )
            now = int(self._clock.now().timestamp())
            if (
                claims.exp <= now
                or claims.iat > now
                or claims.nbf > now
                or claims.token_use != "access"  # noqa: S105 - JWT purpose discriminator
            ):
                raise InvalidCredentials("Invalid access token")
            return AccessClaims(UserId(claims.sub), claims.sid)
        except (jwt.PyJWTError, ValidationError) as error:
            raise InvalidCredentials("Invalid access token") from error


class MemoryRateLimiter:
    """Single-process limiter for tests and explicitly single-process applications."""

    def __init__(self, clock: Clock, limit: int = 10, window_seconds: int = 60) -> None:
        self._clock = clock
        self._limit = limit
        self._window = window_seconds
        self._attempts: dict[str, deque[float]] = {}

    async def require(self, key: str) -> None:
        now = self._clock.now().timestamp()
        # Bound stale key retention as well as each key's queue.
        self._attempts = {
            k: q for k, q in self._attempts.items() if q and q[-1] > now - self._window
        }
        attempts = self._attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - self._window:
            attempts.popleft()
        if len(attempts) >= self._limit:
            raise RateLimitExceeded("Too many attempts")
        attempts.append(now)
