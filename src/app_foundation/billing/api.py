from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from app_foundation.access_control import Resource
from app_foundation.api import Authorize, Scope
from app_foundation.billing import BillingService, CheckoutSession, Customer, Subscription
from app_foundation.primitives import OrganizationId, ValidationError


class CustomerRequest(BaseModel):
    email: str = Field(max_length=254)


class CheckoutRequest(BaseModel):
    price_id: str = Field(min_length=1, max_length=200)
    request_id: UUID


def create_billing_router(
    scope: Scope[BillingService],
    authorize: Authorize,
    success_url: str,
    cancel_url: str,
    allowed_prices: frozenset[str],
) -> APIRouter:
    router = APIRouter(tags=["billing"])

    @router.post("/organizations/{organization_id}/billing/customer")
    async def customer(
        organization_id: UUID, body: CustomerRequest, authorization: str = Header(default="")
    ) -> Customer:
        org = OrganizationId(organization_id)
        await authorize(authorization, "billing.manage", Resource(org))
        async with scope() as service:
            return await service.create_customer(org, body.email)

    @router.post("/organizations/{organization_id}/billing/checkout")
    async def checkout(
        organization_id: UUID, body: CheckoutRequest, authorization: str = Header(default="")
    ) -> CheckoutSession:
        org = OrganizationId(organization_id)
        await authorize(authorization, "billing.manage", Resource(org))
        if body.price_id not in allowed_prices:
            raise ValidationError("Price is not offered by this application")
        async with scope() as service:
            return await service.checkout(
                org, body.price_id, success_url, cancel_url, body.request_id
            )

    @router.post("/organizations/{organization_id}/billing/subscriptions/{subscription_id}/cancel")
    async def cancel(
        organization_id: UUID, subscription_id: UUID, authorization: str = Header(default="")
    ) -> Subscription:
        org = OrganizationId(organization_id)
        await authorize(authorization, "billing.manage", Resource(org))
        async with scope() as service:
            return await service.cancel(org, subscription_id)

    @router.post("/billing/webhook")
    async def webhook(request: Request, stripe_signature: str = Header()) -> dict[str, bool]:
        payload = await request.body()
        if len(payload) > 1048576:
            raise ValidationError("Webhook payload exceeds limit")
        async with scope() as service:
            processed = await service.webhook(payload, stripe_signature)
        return {"processed": processed}

    return router
