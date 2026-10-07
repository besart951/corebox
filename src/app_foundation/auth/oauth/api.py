from fastapi import APIRouter, Header
from pydantic import BaseModel, Field, SecretStr

from app_foundation.api import Authenticate, Scope
from app_foundation.auth import MfaChallenge, TokenPair
from app_foundation.auth.oauth import OAuthService


class OAuthStartRequest(BaseModel):
    browser_binding: SecretStr = Field(min_length=32, max_length=256)


class OAuthCallbackRequest(OAuthStartRequest):
    state: SecretStr = Field(max_length=256)
    code: SecretStr = Field(max_length=4096)


def create_oauth_router(scope: Scope[OAuthService], authenticate: Authenticate) -> APIRouter:
    router = APIRouter(prefix="/auth/google", tags=["oauth"])

    @router.post("/start")
    async def start(body: OAuthStartRequest) -> dict[str, str]:
        async with scope() as service:
            return {"url": await service.begin(body.browser_binding.get_secret_value())}

    @router.post("/link")
    async def link(
        body: OAuthStartRequest, authorization: str = Header(default="")
    ) -> dict[str, str]:
        principal = await authenticate(authorization)
        async with scope() as service:
            return {
                "url": await service.begin(
                    body.browser_binding.get_secret_value(), principal.user_id
                )
            }

    @router.post("/callback")
    async def callback(
        body: OAuthCallbackRequest, authorization: str = Header(default="")
    ) -> TokenPair | MfaChallenge:
        principal = await authenticate(authorization) if authorization else None
        async with scope() as service:
            return await service.complete(
                body.state.get_secret_value(),
                body.code.get_secret_value(),
                body.browser_binding.get_secret_value(),
                principal.user_id if principal else None,
            )

    return router
