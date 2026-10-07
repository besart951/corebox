from uuid import UUID

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from app_foundation.access_control import Resource
from app_foundation.api import Authorize, Scope
from app_foundation.notification import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationService,
)
from app_foundation.primitives import OrganizationId, PageRequest


class PreferenceRequest(BaseModel):
    channel: NotificationChannel
    enabled: bool


def create_notification_router(
    scope: Scope[NotificationService], authorize: Authorize
) -> APIRouter:
    router = APIRouter(
        prefix="/organizations/{organization_id}/notifications", tags=["notifications"]
    )

    @router.get("")
    async def notifications(
        organization_id: UUID,
        authorization: str = Header(default=""),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> tuple[Notification, ...]:
        org = OrganizationId(organization_id)
        principal = await authorize(authorization, "notification.read", Resource(org))
        async with scope() as service:
            return await service.repository.list(org, principal.user_id, PageRequest(limit, offset))

    @router.post("/read-all", status_code=204)
    async def read_all(organization_id: UUID, authorization: str = Header(default="")) -> None:
        org = OrganizationId(organization_id)
        principal = await authorize(authorization, "notification.read", Resource(org))
        async with scope() as service:
            await service.mark_read(org, principal.user_id)

    @router.post("/{notification_id}/read", status_code=204)
    async def read_one(
        organization_id: UUID, notification_id: UUID, authorization: str = Header(default="")
    ) -> None:
        org = OrganizationId(organization_id)
        principal = await authorize(authorization, "notification.read", Resource(org))
        async with scope() as service:
            await service.mark_read(org, principal.user_id, notification_id)

    @router.put("/preferences", status_code=204)
    async def preferences(
        organization_id: UUID, body: PreferenceRequest, authorization: str = Header(default="")
    ) -> None:
        principal = await authorize(
            authorization, "notification.read", Resource(OrganizationId(organization_id))
        )
        async with scope() as service:
            await service.repository.save_preference(
                NotificationPreference(principal.user_id, body.channel, body.enabled)
            )

    return router
