from dataclasses import replace
from datetime import datetime
from uuid import UUID

from app_foundation.auth.models import (
    Credential,
    MfaEnrollment,
    RefreshToken,
    Session,
    VerificationToken,
)
from app_foundation.primitives import Conflict, UserId


class MemoryAuthRepository:
    """Single-task test adapter; concurrency semantics are tested against PostgreSQL."""

    def __init__(self) -> None:
        self.credentials: dict[UserId, Credential] = {}
        self.sessions: dict[UUID, Session] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.verifications: dict[str, VerificationToken] = {}
        self.enrollments: dict[UserId, MfaEnrollment] = {}
        self.identities: dict[tuple[str, str], UserId] = {}

    async def get_credential(self, user_id: UserId) -> Credential | None:
        return self.credentials.get(user_id)

    async def save_credential(self, credential: Credential) -> None:
        self.credentials[credential.user_id] = credential

    async def save_session(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def get_session(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    async def save_refresh(self, token: RefreshToken) -> None:
        self.refresh_tokens[token.digest] = token

    async def refresh_for_update(self, digest: str) -> tuple[RefreshToken, Session] | None:
        token = self.refresh_tokens.get(digest)
        return (token, self.sessions[token.session_id]) if token else None

    async def revoke_user_sessions(self, user_id: UserId) -> None:
        for key, session in tuple(self.sessions.items()):
            if session.user_id == user_id:
                self.sessions[key] = replace(session, revoked=True)

    async def delete_expired_sessions(self, now: datetime) -> None:
        self.sessions = {k: v for k, v in self.sessions.items() if v.expires_at > now}
        self.refresh_tokens = {
            k: v for k, v in self.refresh_tokens.items() if v.session_id in self.sessions
        }

    async def invalidate_verifications(self, user_id: UserId) -> None:
        for digest, token in tuple(self.verifications.items()):
            if token.user_id == user_id:
                self.verifications[digest] = replace(token, consumed=True)

    async def save_verification(self, token: VerificationToken) -> None:
        self.verifications[token.digest] = token

    async def verification_for_update(self, digest: str) -> VerificationToken | None:
        return self.verifications.get(digest)

    async def mfa_for_update(self, user_id: UserId) -> MfaEnrollment | None:
        return self.enrollments.get(user_id)

    async def save_mfa(self, enrollment: MfaEnrollment) -> None:
        self.enrollments[enrollment.user_id] = enrollment

    async def delete_mfa(self, user_id: UserId) -> None:
        self.enrollments.pop(user_id, None)

    async def oauth_user(self, provider: str, subject: str) -> UserId | None:
        return self.identities.get((provider, subject))

    async def link_oauth(self, provider: str, subject: str, user_id: UserId) -> None:
        existing = self.identities.get((provider, subject))
        if existing and existing != user_id:
            raise Conflict("External identity already linked")
        self.identities[provider, subject] = user_id


class MemoryVerificationSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def send(self, email: str, purpose: str, token: str) -> None:
        self.messages.append((email, purpose, token))
