from pydantic import BaseModel
from pydantic import ValidationError as SchemaError
lazy import stripe

from app_foundation.billing import (
    CheckoutSession,
    PaymentEvent,
    ProviderSubscription,
    SubscriptionState,
)
from app_foundation.config import StripeSettings
from app_foundation.primitives import InfrastructureUnavailable, ValidationError


class _Subscription(BaseModel):
    id: str
    customer: str
    status: SubscriptionState


class _EventObject(BaseModel):
    id: str


class _EventData(BaseModel):
    object: _EventObject


class _Event(BaseModel):
    id: str
    type: str
    data: _EventData


class StripePaymentProvider:
    name: str = "stripe"

    def __init__(
        self, settings: StripeSettings, http_client: stripe.HTTPClient | None = None
    ) -> None:
        self._settings = settings
        self._http = http_client or stripe.HTTPXClient(timeout=15)
        self._client = stripe.StripeClient(
            settings.secret_key.get_secret_value(), max_network_retries=2, http_client=self._http
        )

    async def close(self) -> None:
        await self._http.close_async()

    @staticmethod
    def _subscription(value: stripe.Subscription) -> ProviderSubscription:
        parsed = _Subscription.model_validate(
            {"id": value.id, "customer": value.customer, "status": value.status}
        )
        return ProviderSubscription(parsed.id, parsed.customer, parsed.status)

    async def create_customer(self, email: str, key: str) -> str:
        try:
            value = await self._client.v1.customers.create_async(
                {"email": email}, {"idempotency_key": key}
            )
        except stripe.StripeError as error:
            raise InfrastructureUnavailable("Payment customer creation failed") from error
        return value.id

    async def checkout(
        self, customer_id: str, price_id: str, success_url: str, cancel_url: str, key: str
    ) -> CheckoutSession:
        try:
            value = await self._client.v1.checkout.sessions.create_async(
                {
                    "customer": customer_id,
                    "mode": "subscription",
                    "line_items": [{"price": price_id, "quantity": 1}],
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                },
                {"idempotency_key": key},
            )
            if value.url is None:
                raise InfrastructureUnavailable("Provider returned no checkout URL")
            return CheckoutSession(value.id, value.url)
        except stripe.StripeError as error:
            raise InfrastructureUnavailable("Checkout creation failed") from error

    async def create_subscription(
        self, customer_id: str, price_id: str, key: str
    ) -> ProviderSubscription:
        try:
            return self._subscription(
                await self._client.v1.subscriptions.create_async(
                    {
                        "customer": customer_id,
                        "items": [{"price": price_id}],
                        "payment_behavior": "default_incomplete",
                    },
                    {"idempotency_key": key},
                )
            )
        except (stripe.StripeError, SchemaError) as error:
            raise InfrastructureUnavailable("Subscription creation failed") from error

    async def cancel(self, subscription_id: str) -> ProviderSubscription:
        try:
            return self._subscription(
                await self._client.v1.subscriptions.cancel_async(subscription_id)
            )
        except (stripe.StripeError, SchemaError) as error:
            raise InfrastructureUnavailable("Subscription cancellation failed") from error

    async def subscription(self, subscription_id: str) -> ProviderSubscription:
        try:
            return self._subscription(
                await self._client.v1.subscriptions.retrieve_async(subscription_id)
            )
        except (stripe.StripeError, SchemaError) as error:
            raise InfrastructureUnavailable("Subscription lookup failed") from error

    def verify_webhook(self, payload: bytes, signature: str) -> PaymentEvent:
        try:
            stripe.Webhook.construct_event(
                payload, signature, self._settings.webhook_secret.get_secret_value()
            )
            parsed = _Event.model_validate_json(payload)
        except (stripe.SignatureVerificationError, ValueError, SchemaError) as error:
            raise ValidationError("Invalid payment webhook") from error
        return PaymentEvent(
            parsed.id,
            parsed.type,
            parsed.data.object.id if parsed.type.startswith("customer.subscription.") else None,
        )
