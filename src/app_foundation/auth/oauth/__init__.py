import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel

from app_foundation.auth.models import (
    InvalidCredentials,
    MfaChallenge,
    TokenPair,
    VerificationToken,
)
from app_foundation.auth.protocols import OAuthProvider
from app_foundation.auth.service import AuthService, token_digest
from app_foundation.identity import UserService
from app_foundation.primitives import Clock, Conflict, InfrastructureUnavailable, UserId


class _State(BaseModel):
    verifier: str
    nonce: str
    browser_digest: str
    provider: str
    link_user: UUID | None = None


class OAuthStateRepository(Protocol):
    async def save(self, state: str, encrypted_data: str, expires_at: datetime) -> None: ...
    async def consume(self, state: str, now: datetime) -> str | None: ...


class OAuthService:
    def __init__(
        self,
        auth: AuthService,
        users: UserService,
        provider: OAuthProvider,
        clock: Clock,
        encryption_key: bytes,
        state_repository: OAuthStateRepository,
    ) -> None:
        self.state_repository = state_repository
        self._auth = auth
        self._users = users
        self._provider = provider
        self._clock = clock
        self._cipher = Fernet(encryption_key)

    async def begin(self, browser_binding: str, link_user: UserId | None = None) -> str:
        state, verifier, nonce = token_urlsafe(32), token_urlsafe(48), token_urlsafe(32)
        data = _State(
            verifier=verifier,
            nonce=nonce,
            browser_digest=token_digest(browser_binding),
            provider=self._provider.name,
            link_user=link_user,
        )
        # Pre-login state is stored independently of users.
        await self._state_store.save(
            state,
            self._cipher.encrypt(data.model_dump_json().encode()).decode(),
            self._clock.now() + timedelta(minutes=10),
        )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return self._provider.authorization_url(state, challenge, nonce)

    @property
    def _state_store(self) -> OAuthStateRepository:
        return self.state_repository

    async def complete(
        self, state: str, code: str, browser_binding: str, authenticated_user: UserId | None = None
    ) -> TokenPair | MfaChallenge:
        payload = await self._state_store.consume(state, self._clock.now())
        if payload is None:
            raise InvalidCredentials("Invalid OAuth state")
        try:
            data = _State.model_validate_json(self._cipher.decrypt(payload.encode()))
        except (InvalidToken, ValueError) as error:
            raise InfrastructureUnavailable("OAuth state cannot be decrypted") from error
        if (
            not hmac.compare_digest(data.browser_digest, token_digest(browser_binding))
            or data.provider != self._provider.name
        ):
            raise InvalidCredentials("Invalid OAuth state")
        identity = await self._provider.authenticate(code, data.verifier, data.nonce)
        if not identity.email_verified:
            raise InvalidCredentials("Provider email is not verified")
        user_id = await self._auth.repository.oauth_user(identity.provider, identity.subject)
        if data.link_user:
            if authenticated_user != data.link_user:
                raise InvalidCredentials(
                    "Account linking requires the initiating authenticated user"
                )
            if user_id and user_id != authenticated_user:
                raise Conflict("External identity already linked")
            user_id = UserId(data.link_user)
            if await self._auth.repository.oauth_user(identity.provider, identity.subject) is None:
                await self._auth.repository.link_oauth(identity.provider, identity.subject, user_id)
        elif user_id is None:
            if await self._users.repository.get_by_email(identity.email):
                raise Conflict("Sign in to the existing account to link this provider")
            user = await self._users.create(identity.email, identity.display_name)
            user_id = user.id
            await self._auth.repository.link_oauth(identity.provider, identity.subject, user_id)
        enrollment = await self._auth.repository.mfa_for_update(user_id)
        if enrollment and enrollment.confirmed:
            raw = token_urlsafe(32)
            await self._auth.repository.save_verification(
                VerificationToken(
                    token_digest(raw),
                    user_id,
                    "mfa-login",
                    self._clock.now() + timedelta(minutes=5),
                )
            )
            return MfaChallenge(raw)
        return await self._auth.create_session(user_id)
