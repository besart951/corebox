import base64
import hashlib
import hmac
import struct
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid7

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app_foundation.auth import AuthService, InvalidCredentials, MfaChallenge, TokenPair
from app_foundation.auth.adapters import Argon2PasswordHasher, JwtTokenIssuer, MemoryRateLimiter
from app_foundation.auth.memory import MemoryAuthRepository, MemoryVerificationSender
from app_foundation.auth.mfa import MfaService
from app_foundation.auth.models import OAuthIdentity
from app_foundation.auth.oauth import OAuthService
from app_foundation.auth.oauth.state import MemoryOAuthStateRepository
from app_foundation.config import JwtSettings
from app_foundation.events import InProcessEventPublisher
from app_foundation.identity import UserService
from app_foundation.identity.memory import MemoryUserRepository
from app_foundation.primitives import FixedClock, UUID7Generator


def totp(secret: str, instant: datetime) -> str:
    digest = hmac.new(
        base64.b32decode(secret), struct.pack(">Q", int(instant.timestamp()) // 30), hashlib.sha1
    ).digest()
    offset = digest[-1] & 15
    return str((int.from_bytes(digest[offset : offset + 4]) & 0x7FFFFFFF) % 1000000).zfill(6)


async def test_mfa_enrollment_replay_recovery_and_disable() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    repository, sender = MemoryAuthRepository(), MemoryVerificationSender()
    users = UserService(MemoryUserRepository(), clock, UUID7Generator(), InProcessEventPublisher())
    passwords, limiter = Argon2PasswordHasher(), MemoryRateLimiter(clock, limit=100)
    auth = AuthService(
        users,
        repository,
        passwords,
        JwtTokenIssuer(JwtSettings(secret=SecretStr("a" * 32)), clock),
        limiter,
        sender,
        clock,
        UUID7Generator(),
        InProcessEventPublisher(),
    )
    user = await auth.register("mfa@example.com", "correct-password", "MFA")
    await auth.verify_email(sender.messages[-1][2])
    mfa = MfaService(repository, passwords, limiter, Fernet.generate_key(), clock)
    uri = await mfa.enroll(user.id, "correct-password", user.email, "Test")
    secret = parse_qs(urlparse(uri).query)["secret"][0]
    code = totp(secret, clock.now())
    recovery = await mfa.confirm(user.id, code)
    assert not await mfa.verify(user.id, code)
    assert all(c not in repository.enrollments[user.id].recovery_digests for c in recovery)
    challenge = await auth.login(user.email, "correct-password")
    assert isinstance(challenge, MfaChallenge)
    pair = await auth.complete_mfa(challenge.token, recovery[0], mfa)
    assert isinstance(pair, TokenPair)
    assert not await mfa.verify(user.id, recovery[0])
    with pytest.raises(InvalidCredentials):
        await mfa.disable(user.id, "wrong-password", recovery[1])
    await mfa.disable(user.id, "correct-password", recovery[1])
    with pytest.raises(InvalidCredentials):
        await auth.authenticate(pair.access_token)


class FakeOAuthProvider:
    name: str = "test"

    def authorization_url(self, state: str, challenge: str, nonce: str) -> str:
        return f"https://provider.example/auth?state={state}&challenge={challenge}&nonce={nonce}"

    async def authenticate(self, code: str, verifier: str, nonce: str) -> OAuthIdentity:
        assert code and verifier and nonce
        return OAuthIdentity("test", "subject", "oauth@example.com", True, "OAuth")


async def test_oauth_state_binding_and_single_use() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    users = UserService(MemoryUserRepository(), clock, UUID7Generator(), InProcessEventPublisher())
    auth = AuthService(
        users,
        MemoryAuthRepository(),
        Argon2PasswordHasher(),
        JwtTokenIssuer(JwtSettings(secret=SecretStr("a" * 32)), clock),
        MemoryRateLimiter(clock),
        MemoryVerificationSender(),
        clock,
        UUID7Generator(),
        InProcessEventPublisher(),
    )
    oauth = OAuthService(
        auth, users, FakeOAuthProvider(), clock, Fernet.generate_key(), MemoryOAuthStateRepository()
    )
    binding = uuid7().hex
    url = await oauth.begin(binding)
    state = parse_qs(urlparse(url).query)["state"][0]
    with pytest.raises(InvalidCredentials):
        await oauth.complete(state, "code", "wrong-binding")
    url = await oauth.begin(binding)
    state = parse_qs(urlparse(url).query)["state"][0]
    pair = await oauth.complete(state, "code", binding)
    assert isinstance(pair, TokenPair)
    with pytest.raises(InvalidCredentials):
        await oauth.complete(state, "code", binding)


async def test_mfa_non_ascii_code_is_rejected() -> None:
    from app_foundation.auth.models import MfaEnrollment
    from app_foundation.primitives import UserId

    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    repository = MemoryAuthRepository()
    key = Fernet.generate_key()
    user_id = UserId(uuid7())
    await repository.save_mfa(
        MfaEnrollment(user_id, Fernet(key).encrypt(b"JBSWY3DPEHPK3PXP").decode(), True, ())
    )
    mfa = MfaService(repository, Argon2PasswordHasher(), MemoryRateLimiter(clock), key, clock)
    assert not await mfa.verify(user_id, "１２３４５６")  # noqa: RUF001 - intentional Unicode input
