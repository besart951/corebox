from fastapi import APIRouter, Header
from pydantic import BaseModel, Field, SecretStr

from app_foundation.api import Authenticate, Scope, bearer
from app_foundation.auth import (
    AuthenticationRejected,
    AuthService,
    InvalidCredentials,
    MfaChallenge,
    TokenPair,
)
from app_foundation.auth.mfa import MfaService
from app_foundation.identity.api import UserResponse


class RegistrationRequest(BaseModel):
    email: str = Field(max_length=254)
    password: SecretStr = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: SecretStr = Field(max_length=1024)


class TokenRequest(BaseModel):
    token: SecretStr = Field(max_length=4096)


class EmailRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetRequest(TokenRequest):
    password: SecretStr = Field(min_length=12, max_length=1024)


class MfaLoginRequest(TokenRequest):
    code: SecretStr = Field(max_length=128)


class PasswordRequest(BaseModel):
    password: SecretStr = Field(max_length=1024)


class CodeRequest(BaseModel):
    code: SecretStr = Field(max_length=128)


class DisableMfaRequest(PasswordRequest, CodeRequest):
    pass


def create_auth_router(scope: Scope[AuthService]) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", status_code=201)
    async def register(body: RegistrationRequest) -> UserResponse:
        async with scope() as service:
            return UserResponse.model_validate(
                await service.register(
                    body.email, body.password.get_secret_value(), body.display_name
                )
            )

    @router.post("/login")
    async def login(body: LoginRequest) -> TokenPair | MfaChallenge:
        async with scope() as service:
            return await service.login(body.email, body.password.get_secret_value())

    @router.post("/refresh")
    async def refresh(body: TokenRequest) -> TokenPair:
        async with scope() as service:
            result = await service.refresh(body.token.get_secret_value())
        if isinstance(result, AuthenticationRejected):
            raise InvalidCredentials("Invalid credentials")
        return result

    @router.post("/logout", status_code=204)
    async def logout(authorization: str = Header(default="")) -> None:
        async with scope() as service:
            await service.logout(bearer(authorization))

    @router.post("/verify-email", status_code=204)
    async def verify(body: TokenRequest) -> None:
        async with scope() as service:
            await service.verify_email(body.token.get_secret_value())

    @router.post("/request-verification", status_code=202)
    async def request_verification(body: EmailRequest) -> None:
        async with scope() as service:
            await service.request_verification(body.email, "verify-email")

    @router.post("/request-password-reset", status_code=202)
    async def request_reset(body: EmailRequest) -> None:
        async with scope() as service:
            await service.request_verification(body.email, "reset-password")

    @router.post("/reset-password", status_code=204)
    async def reset(body: ResetRequest) -> None:
        async with scope() as service:
            await service.reset_password(
                body.token.get_secret_value(), body.password.get_secret_value()
            )

    return router


def create_mfa_router(
    scope: Scope[tuple[AuthService, MfaService]], authenticate: Authenticate, issuer: str
) -> APIRouter:
    router = APIRouter(prefix="/auth/mfa", tags=["mfa"])

    @router.post("/enroll")
    async def enroll(
        body: PasswordRequest, authorization: str = Header(default="")
    ) -> dict[str, str]:
        principal = await authenticate(authorization)
        async with scope() as (auth, mfa):
            user = await auth.authenticate(bearer(authorization))
            return {
                "otpauth_uri": await mfa.enroll(
                    principal.user_id, body.password.get_secret_value(), user.email, issuer
                )
            }

    @router.post("/confirm")
    async def confirm(
        body: CodeRequest, authorization: str = Header(default="")
    ) -> tuple[str, ...]:
        principal = await authenticate(authorization)
        async with scope() as (_, mfa):
            return await mfa.confirm(principal.user_id, body.code.get_secret_value())

    @router.post("/verify")
    async def verify(body: MfaLoginRequest) -> TokenPair:
        async with scope() as (auth, mfa):
            return await auth.complete_mfa(
                body.token.get_secret_value(), body.code.get_secret_value(), mfa
            )

    @router.post("/disable", status_code=204)
    async def disable(body: DisableMfaRequest, authorization: str = Header(default="")) -> None:
        principal = await authenticate(authorization)
        async with scope() as (_, mfa):
            await mfa.disable(
                principal.user_id, body.password.get_secret_value(), body.code.get_secret_value()
            )

    return router
