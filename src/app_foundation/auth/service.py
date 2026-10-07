from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe

from app_foundation.auth.models import (
    AuthenticationRejected,
    Credential,
    InvalidCredentials,
    MfaChallenge,
    RefreshToken,
    Session,
    TokenPair,
    TokenPurpose,
    VerificationToken,
)
from app_foundation.auth.protocols import (
    AuthRepository,
    PasswordHasher,
    RateLimiter,
    SecondFactor,
    TokenIssuer,
    VerificationSender,
)
from app_foundation.events import ApplicationEvent, EventPublisher
from app_foundation.identity import User, UserService, normalize_email
from app_foundation.primitives import Clock, IdGenerator, UserId, ValidationError


def token_digest(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 1024:
        raise ValidationError("Password must contain 12..1024 characters")


class AuthService:
    def __init__(
        self,
        users: UserService,
        repository: AuthRepository,
        passwords: PasswordHasher,
        tokens: TokenIssuer,
        limiter: RateLimiter,
        sender: VerificationSender,
        clock: Clock,
        ids: IdGenerator,
        events: EventPublisher,
        refresh_seconds: int = 2592000,
    ) -> None:
        self._users = users
        self.repository = repository
        self._passwords = passwords
        self._tokens = tokens
        self._limiter = limiter
        self._sender = sender
        self._clock = clock
        self._ids = ids
        self._events = events
        self._refresh_seconds = refresh_seconds

    async def register(self, email: str, password: str, display_name: str) -> User:
        await self._limiter.require("register:" + token_digest(normalize_email(email)))
        validate_password(password)
        user = await self._users.create(email, display_name)
        await self.repository.save_credential(
            Credential(user.id, await self._passwords.hash(password))
        )
        await self.request_verification(user.email, "verify-email")
        return user

    async def login(self, email: str, password: str) -> TokenPair | MfaChallenge:
        normalized = normalize_email(email)
        await self._limiter.require("login:" + token_digest(normalized))
        user = await self._users.repository.get_by_email(normalized)
        credential = await self.repository.get_credential(user.id) if user else None
        if not user or not credential:
            # Perform the expensive operation on unknown users to reduce enumeration timing.
            await self._passwords.hash(password[:1024])
            raise InvalidCredentials("Invalid credentials")
        if (
            not await self._passwords.verify(password, credential.password_hash)
            or not user.active
            or not credential.email_verified
        ):
            raise InvalidCredentials("Invalid credentials")
        mfa = await self.repository.mfa_for_update(user.id)
        if mfa and mfa.confirmed:
            return MfaChallenge(await self._verification(user.id, "mfa-login", seconds=300))
        return await self.create_session(user.id)

    async def complete_mfa(self, challenge: str, code: str, factor: SecondFactor) -> TokenPair:
        await self._limiter.require("mfa:" + token_digest(challenge))
        token = await self._valid_verification(challenge, "mfa-login")
        if not await factor.verify(token.user_id, code):
            raise InvalidCredentials("Invalid second factor")
        await self.repository.save_verification(replace(token, consumed=True))
        return await self.create_session(token.user_id)

    async def create_session(self, user_id: UserId) -> TokenPair:
        if not (await self._users.get(user_id)).active:
            raise InvalidCredentials("Inactive user")
        session = Session(
            self._ids.new(), user_id, self._clock.now() + timedelta(seconds=self._refresh_seconds)
        )
        await self.repository.save_session(session)
        return await self._pair(session)

    async def _pair(self, session: Session) -> TokenPair:
        refresh = token_urlsafe(48)
        await self.repository.save_refresh(RefreshToken(token_digest(refresh), session.id))
        return TokenPair(
            self._tokens.issue(session.user_id, session.id), refresh, self._tokens.access_seconds
        )

    async def refresh(self, raw: str) -> TokenPair | AuthenticationRejected:
        await self._limiter.require("refresh:" + token_digest(raw))
        found = await self.repository.refresh_for_update(token_digest(raw))
        if found is None:
            return AuthenticationRejected()
        token, session = found
        if token.consumed:
            await self.repository.save_session(replace(session, revoked=True))
            return AuthenticationRejected()
        user = await self._users.get(session.user_id)
        if session.revoked or session.expires_at <= self._clock.now() or not user.active:
            return AuthenticationRejected()
        await self.repository.save_refresh(replace(token, consumed=True))
        return await self._pair(session)

    async def authenticate(self, access_token: str) -> User:
        claims = self._tokens.validate(access_token)
        session = await self.repository.get_session(claims.session_id)
        if (
            not session
            or session.revoked
            or session.user_id != claims.user_id
            or session.expires_at <= self._clock.now()
        ):
            raise InvalidCredentials("Invalid session")
        user = await self._users.get(claims.user_id)
        if not user.active:
            raise InvalidCredentials("Inactive user")
        return user

    async def logout(self, access_token: str) -> None:
        claims = self._tokens.validate(access_token)
        session = await self.repository.get_session(claims.session_id)
        if session and session.user_id == claims.user_id:
            await self.repository.save_session(replace(session, revoked=True))

    async def _verification(
        self, user_id: UserId, purpose: TokenPurpose, seconds: int = 1800
    ) -> str:
        raw = token_urlsafe(32)
        await self.repository.save_verification(
            VerificationToken(
                token_digest(raw), user_id, purpose, self._clock.now() + timedelta(seconds=seconds)
            )
        )
        return raw

    async def request_verification(self, email: str, purpose: TokenPurpose) -> None:
        if purpose not in ("verify-email", "reset-password"):
            raise ValidationError("Unsupported public verification purpose")
        normalized = normalize_email(email)
        await self._limiter.require(purpose + ":" + token_digest(normalized))
        user = await self._users.repository.get_by_email(normalized)
        if user and user.active:
            raw = await self._verification(user.id, purpose)
            await self._sender.send(user.email, purpose, raw)
            await self._events.publish(
                (
                    ApplicationEvent(
                        "password.reset_requested"
                        if purpose == "reset-password"
                        else "email.verification_requested",
                        user.id,
                        self._clock.now(),
                    ),
                )
            )

    async def _valid_verification(self, raw: str, purpose: TokenPurpose) -> VerificationToken:
        token = await self.repository.verification_for_update(token_digest(raw))
        if (
            not token
            or token.purpose != purpose
            or token.consumed
            or token.expires_at <= self._clock.now()
        ):
            raise InvalidCredentials("Invalid or expired verification token")
        return token

    async def verify_email(self, raw: str) -> None:
        await self._limiter.require("verify:" + token_digest(raw))
        token = await self._valid_verification(raw, "verify-email")
        credential = await self.repository.get_credential(token.user_id)
        if credential is None:
            raise InvalidCredentials("Invalid credentials")
        await self.repository.save_credential(replace(credential, email_verified=True))
        await self.repository.save_verification(replace(token, consumed=True))

    async def reset_password(self, raw: str, password: str) -> None:
        await self._limiter.require("reset:" + token_digest(raw))
        validate_password(password)
        token = await self._valid_verification(raw, "reset-password")
        await self.repository.save_credential(
            Credential(token.user_id, await self._passwords.hash(password), True)
        )
        await self.repository.save_verification(replace(token, consumed=True))
        await self.repository.invalidate_verifications(token.user_id)
        await self.repository.revoke_user_sessions(token.user_id)
