from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app_foundation.primitives import FoundationError, UserId


class InvalidCredentials(FoundationError):
    pass


class RateLimitExceeded(FoundationError):
    pass


@dataclass(frozen=True, slots=True)
class Credential:
    user_id: UserId
    password_hash: str
    email_verified: bool = False


@dataclass(frozen=True, slots=True)
class Session:
    id: UUID
    user_id: UserId
    expires_at: datetime
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class RefreshToken:
    digest: str
    session_id: UUID
    consumed: bool = False


type TokenPurpose = Literal["verify-email", "reset-password", "mfa-login", "oauth-state"]


@dataclass(frozen=True, slots=True)
class VerificationToken:
    digest: str
    user_id: UserId
    purpose: TokenPurpose
    expires_at: datetime
    consumed: bool = False
    data: str = ""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"  # noqa: S105 - protocol discriminator, not a secret


@dataclass(frozen=True, slots=True)
class AuthenticationRejected:
    """Commit security state (e.g. family revocation) before reporting rejection."""

    reason: str = "Invalid credentials"


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    token: str


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UserId
    session_id: UUID


@dataclass(frozen=True, slots=True)
class MfaEnrollment:
    user_id: UserId
    encrypted_secret: str
    confirmed: bool
    recovery_digests: tuple[str, ...]
    last_counter: int = -1


@dataclass(frozen=True, slots=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str
    email_verified: bool
    display_name: str
