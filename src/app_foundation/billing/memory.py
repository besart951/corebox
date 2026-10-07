from dataclasses import replace
from uuid import UUID

from app_foundation.billing import (
    CheckoutSession,
    Customer,
    PaymentEvent,
    ProviderSubscription,
    Subscription,
    SubscriptionState,
)
from app_foundation.primitives import OrganizationId, ValidationError


class MemoryBillingRepository:
    def __init__(self) -> None:
        self.customers: dict[UUID, Customer] = {}
        self.items: dict[UUID, Subscription] = {}
        self.events: set[tuple[str, str]] = set()

    async def save_customer(self, customer: Customer) -> None:
        self.customers[customer.id] = customer

    async def customer(self, organization_id: OrganizationId) -> Customer | None:
        return next(
            (c for c in self.customers.values() if c.organization_id == organization_id), None
        )

    async def customer_by_provider(self, provider_id: str) -> Customer | None:
        return next((c for c in self.customers.values() if c.provider_id == provider_id), None)

    async def save_subscription(self, subscription: Subscription) -> None:
        self.items[subscription.id] = subscription

    async def subscription(
        self, organization_id: OrganizationId, subscription_id: UUID
    ) -> Subscription | None:
        item = self.items.get(subscription_id)
        return item if item and item.organization_id == organization_id else None

    async def subscription_by_provider(self, provider_id: str) -> Subscription | None:
        return next((s for s in self.items.values() if s.provider_id == provider_id), None)

    async def claim_event(self, provider: str, event_id: str) -> bool:
        if (provider, event_id) in self.events:
            return False
        self.events.add((provider, event_id))
        return True

    async def lock_customer(self, customer_id: UUID) -> None:
        if customer_id not in self.customers:
            raise ValidationError("Unknown customer")

    async def subscriptions(self) -> tuple[Subscription, ...]:
        return tuple(self.items.values())


class FakePaymentProvider:
    name: str = "fake"

    def __init__(self) -> None:
        self.items: dict[str, ProviderSubscription] = {}
        self.events: dict[bytes, PaymentEvent] = {}

    async def create_customer(self, email: str, key: str) -> str:
        return "customer_" + key + "_" + email

    async def checkout(
        self, customer_id: str, price_id: str, success_url: str, cancel_url: str, key: str
    ) -> CheckoutSession:
        if not all((customer_id, price_id, cancel_url)):
            raise ValidationError("Missing checkout input")
        return CheckoutSession(key, success_url)

    async def create_subscription(
        self, customer_id: str, price_id: str, key: str
    ) -> ProviderSubscription:
        if not price_id:
            raise ValidationError("Missing price")
        self.items.setdefault(key, ProviderSubscription(key, customer_id, SubscriptionState.ACTIVE))
        return self.items[key]

    async def cancel(self, subscription_id: str) -> ProviderSubscription:
        self.items[subscription_id] = replace(
            self.items[subscription_id], state=SubscriptionState.CANCELED
        )
        return self.items[subscription_id]

    async def subscription(self, subscription_id: str) -> ProviderSubscription:
        return self.items[subscription_id]

    def verify_webhook(self, payload: bytes, signature: str) -> PaymentEvent:
        if signature != "fake-valid-signature":
            raise ValidationError("Invalid fake signature")
        return self.events[payload]
