from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field

from app_foundation.access_control import Resource
from app_foundation.api import Authorize, Scope
from app_foundation.identity import UserService
from app_foundation.primitives import UserId


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
    first_name: str
    last_name: str
    preferred_locale: str
    timezone: str
    active: bool
    created_at: datetime
    updated_at: datetime


class ProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    first_name: str = Field(default="", max_length=200)
    last_name: str = Field(default="", max_length=200)
    preferred_locale: str = Field(default="en", max_length=30)
    timezone: str = Field(default="UTC", max_length=100)


def create_user_router(scope: Scope[UserService], authorize: Authorize) -> APIRouter:
    router = APIRouter(prefix="/users", tags=["users"])

    @router.get("/{user_id}")
    async def get_user(user_id: UUID, authorization: str = Header(default="")) -> UserResponse:
        await authorize(authorization, "user.read", Resource(owner_id=UserId(user_id)))
        async with scope() as service:
            return UserResponse.model_validate(await service.get(UserId(user_id)))

    @router.patch("/{user_id}")
    async def update_user(
        user_id: UUID, body: ProfileRequest, authorization: str = Header(default="")
    ) -> UserResponse:
        await authorize(authorization, "user.write", Resource(owner_id=UserId(user_id)))
        async with scope() as service:
            user = await service.update_profile(
                UserId(user_id),
                display_name=body.display_name,
                first_name=body.first_name,
                last_name=body.last_name,
                preferred_locale=body.preferred_locale,
                timezone=body.timezone,
            )
            return UserResponse.model_validate(user)

    @router.delete("/{user_id}", status_code=204)
    async def deactivate_user(user_id: UUID, authorization: str = Header(default="")) -> None:
        await authorize(authorization, "user.write", Resource(owner_id=UserId(user_id)))
        async with scope() as service:
            await service.deactivate(UserId(user_id))

    return router
