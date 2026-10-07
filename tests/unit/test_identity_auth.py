from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from app_foundation.auth import AuthenticationRejected, AuthService, InvalidCredentials, TokenPair
from app_foundation.auth.adapters import Argon2PasswordHasher, JwtTokenIssuer, MemoryRateLimiter
from app_foundation.auth.memory import MemoryAuthRepository, MemoryVerificationSender
from app_foundation.config import JwtSettings
from app_foundation.events import InProcessEventPublisher
from app_foundation.identity import EmailAlreadyExists, UserService
from app_foundation.identity.memory import MemoryUserRepository
from app_foundation.primitives import FixedClock, UUID7Generator


async def test_identity_uniqueness_and_immutable_update() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    users = UserService(MemoryUserRepository(), clock, UUID7Generator(), InProcessEventPublisher())
    user = await users.create(" PERSON@Example.com ", "Person")
    assert user.email == "person@example.com"
    with pytest.raises(EmailAlreadyExists):
        await users.create("person@example.com", "Other")
    updated = await users.update_profile(user.id, display_name="Changed")
    assert user.display_name == "Person"
    assert updated.display_name == "Changed"
    assert not (await users.deactivate(user.id)).active


async def test_auth_rotation_replay_reset_and_disabled_user() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    events = InProcessEventPublisher()
    users = UserService(MemoryUserRepository(), clock, UUID7Generator(), events)
    repository = MemoryAuthRepository()
    sender = MemoryVerificationSender()
    issuer = JwtTokenIssuer(
        JwtSettings(secret=SecretStr("test-key-with-at-least-thirty-two-characters")), clock
    )
    auth = AuthService(
        users,
        repository,
        Argon2PasswordHasher(),
        issuer,
        MemoryRateLimiter(clock),
        sender,
        clock,
        UUID7Generator(),
        events,
    )
    user = await auth.register("person@example.com", "correct-password-value", "Person")
    with pytest.raises(InvalidCredentials):
        await auth.login(user.email, "correct-password-value")
    await auth.verify_email(sender.messages[-1][2])
    pair = await auth.login(user.email, "correct-password-value")
    assert isinstance(pair, TokenPair)
    assert (await auth.authenticate(pair.access_token)).id == user.id
    rotated = await auth.refresh(pair.refresh_token)
    assert isinstance(rotated, TokenPair)
    assert isinstance(await auth.refresh(pair.refresh_token), AuthenticationRejected)
    with pytest.raises(InvalidCredentials):
        await auth.authenticate(rotated.access_token)
    await auth.request_verification(user.email, "reset-password")
    reset = sender.messages[-1][2]
    await auth.reset_password(reset, "replacement-password-value")
    with pytest.raises(InvalidCredentials):
        await auth.reset_password(reset, "another-password-value")
    pair = await auth.login(user.email, "replacement-password-value")
    assert isinstance(pair, TokenPair)
    await users.repository.save(replace(user, active=False))
    with pytest.raises(InvalidCredentials):
        await auth.authenticate(pair.access_token)
