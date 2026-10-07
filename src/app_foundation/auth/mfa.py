import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import replace
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken

from app_foundation.auth.models import InvalidCredentials, MfaEnrollment
from app_foundation.auth.protocols import AuthRepository, PasswordHasher, RateLimiter
from app_foundation.auth.service import token_digest
from app_foundation.primitives import Clock, Conflict, InfrastructureUnavailable, UserId


class MfaService:
    def __init__(
        self,
        repository: AuthRepository,
        passwords: PasswordHasher,
        limiter: RateLimiter,
        encryption_key: bytes,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._passwords = passwords
        self._limiter = limiter
        self._cipher = Fernet(encryption_key)
        self._clock = clock

    async def _reauthenticate(self, user_id: UserId, password: str) -> None:
        await self._limiter.require("reauth:" + str(user_id))
        credential = await self._repository.get_credential(user_id)
        if not credential or not await self._passwords.verify(password, credential.password_hash):
            raise InvalidCredentials("Invalid credentials")

    async def enroll(self, user_id: UserId, password: str, account: str, issuer: str) -> str:
        await self._reauthenticate(user_id, password)
        existing = await self._repository.mfa_for_update(user_id)
        if existing and existing.confirmed:
            raise Conflict("MFA already enabled")
        secret = base64.b32encode(secrets.token_bytes(20)).decode()
        await self._repository.save_mfa(
            MfaEnrollment(user_id, self._cipher.encrypt(secret.encode()).decode(), False, ())
        )
        return (
            "otpauth://totp/"
            + quote(f"{issuer}:{account}", safe="")
            + "?"
            + urlencode(
                {
                    "secret": secret,
                    "issuer": issuer,
                    "algorithm": "SHA1",
                    "digits": "6",
                    "period": "30",
                }
            )
        )

    def _counter(self, enrollment: MfaEnrollment, code: str) -> int | None:
        if len(code) != 6 or not code.isascii() or not code.isdecimal():
            return None
        try:
            secret = base64.b32decode(self._cipher.decrypt(enrollment.encrypted_secret.encode()))
        except InvalidToken as error:
            raise InfrastructureUnavailable("MFA key cannot decrypt enrollment") from error
        current = int(self._clock.now().timestamp()) // 30
        for counter in (current - 1, current, current + 1):
            digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
            offset = digest[-1] & 15
            expected = str(
                (int.from_bytes(digest[offset : offset + 4]) & 0x7FFFFFFF) % 1000000
            ).zfill(6)
            if counter > enrollment.last_counter and hmac.compare_digest(expected, code):
                return counter
        return None

    async def confirm(self, user_id: UserId, code: str) -> tuple[str, ...]:
        await self._limiter.require("mfa:" + str(user_id))
        enrollment = await self._repository.mfa_for_update(user_id)
        if not enrollment or enrollment.confirmed:
            raise InvalidCredentials("No pending enrollment")
        counter = self._counter(enrollment, code)
        if counter is None:
            raise InvalidCredentials("Invalid second factor")
        codes = tuple(secrets.token_hex(16) for _ in range(10))
        await self._repository.save_mfa(
            replace(
                enrollment,
                confirmed=True,
                last_counter=counter,
                recovery_digests=tuple(token_digest(c) for c in codes),
            )
        )
        return codes

    async def verify(self, user_id: UserId, code: str) -> bool:
        await self._limiter.require("mfa:" + str(user_id))
        enrollment = await self._repository.mfa_for_update(user_id)
        if not enrollment or not enrollment.confirmed:
            return False
        digest = token_digest(code)
        recovery = next(
            (d for d in enrollment.recovery_digests if hmac.compare_digest(d, digest)), None
        )
        if recovery:
            await self._repository.save_mfa(
                replace(
                    enrollment,
                    recovery_digests=tuple(d for d in enrollment.recovery_digests if d != recovery),
                )
            )
            return True
        counter = self._counter(enrollment, code)
        if counter is None:
            return False
        await self._repository.save_mfa(replace(enrollment, last_counter=counter))
        return True

    async def disable(self, user_id: UserId, password: str, code: str) -> None:
        await self._reauthenticate(user_id, password)
        if not await self.verify(user_id, code):
            raise InvalidCredentials("Invalid second factor")
        await self._repository.delete_mfa(user_id)
        await self._repository.revoke_user_sessions(user_id)
