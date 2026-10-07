from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app_foundation.events import ApplicationEvent, EventPublisher
from app_foundation.primitives import Clock, IdGenerator, NotFound, OrganizationId, ValidationError


class SubscriptionState(StrEnum):
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class Customer:
    id: UUID
    organization_id: OrganizationId
    email: str
    provider_id: str


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    name: str
    provider_id: str


@dataclass(frozen=True, slots=True)
class Price:
    id: UUID
    product_id: UUID
    provider_id: str
    currency: str
    amount_minor: int
    recurring: bool = True

    def __post_init__(self) -> None:
        if self.amount_minor < 0 or len(self.currency) != 3:
            raise ValidationError("Invalid price")


@dataclass(frozen=True, slots=True)
class InvoiceReference:
    provider_id: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class Subscription:
    id: UUID
    organization_id: OrganizationId
    customer_id: UUID
    provider_id: str
    state: SubscriptionState
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    provider_id: str
    url: str


@dataclass(frozen=True, slots=True)
class ProviderSubscription:
    provider_id: str
    customer_provider_id: str
    state: SubscriptionState


@dataclass(frozen=True, slots=True)
class PaymentEvent:
    provider_event_id: str
    event_type: str
    subscription_provider_id: str | None


class PaymentProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def create_customer(self, email: str, key: str) -> str: ...
    async def checkout(
        self, customer_id: str, price_id: str, success_url: str, cancel_url: str, key: str
    ) -> CheckoutSession: ...
    async def create_subscription(
        self, customer_id: str, price_id: str, key: str
    ) -> ProviderSubscription: ...
    async def cancel(self, subscription_id: str) -> ProviderSubscription: ...
    async def subscription(self, subscription_id: str) -> ProviderSubscription: ...
    def verify_webhook(self, payload: bytes, signature: str) -> PaymentEvent: ...


class BillingRepository(Protocol):
    async def save_customer(self, customer: Customer) -> None: ...
    async def customer(self, organization_id: OrganizationId) -> Customer | None: ...
    async def customer_by_provider(self, provider_id: str) -> Customer | None: ...
    async def save_subscription(self, subscription: Subscription) -> None: ...
    async def subscription(
        self, organization_id: OrganizationId, subscription_id: UUID
    ) -> Subscription | None: ...
    async def subscription_by_provider(self, provider_id: str) -> Subscription | None: ...
    async def claim_event(self, provider: str, event_id: str) -> bool: ...
    async def lock_customer(self, customer_id: UUID) -> None: ...
    async def subscriptions(self) -> tuple[Subscription, ...]: ...


class BillingService:
    def __init__(
        self,
        repository: BillingRepository,
        provider: PaymentProvider,
        ids: IdGenerator,
        clock: Clock,
        events: EventPublisher,
    ) -> None:
        self.repository = repository
        self._provider = provider
        self._ids = ids
        self._clock = clock
        self._events = events

    async def create_customer(self, organization_id: OrganizationId, email: str) -> Customer:
        existing = await self.repository.customer(organization_id)
        if existing:
            return existing
        external = await self._provider.create_customer(email, f"customer:{organization_id}")
        customer = Customer(self._ids.new(), organization_id, email, external)
        await self.repository.save_customer(customer)
        return customer

    async def checkout(
        self,
        organization_id: OrganizationId,
        price_id: str,
        success_url: str,
        cancel_url: str,
        request_id: UUID,
    ) -> CheckoutSession:
        customer = await self.repository.customer(organization_id)
        if customer is None:
            raise NotFound("Billing customer not found")
        return await self._provider.checkout(
            customer.provider_id,
            price_id,
            success_url,
            cancel_url,
            f"checkout:{organization_id}:{request_id}",
        )

    async def subscribe(
        self, organization_id: OrganizationId, price_id: str, request_id: UUID
    ) -> Subscription:
        customer = await self.repository.customer(organization_id)
        if customer is None:
            raise NotFound("Billing customer not found")
        await self.repository.lock_customer(customer.id)
        external = await self._provider.create_subscription(
            customer.provider_id, price_id, f"subscription:{organization_id}:{request_id}"
        )
        return await self._save(customer, external)

    async def cancel(self, organization_id: OrganizationId, subscription_id: UUID) -> Subscription:
        subscription = await self.repository.subscription(organization_id, subscription_id)
        if subscription is None:
            raise NotFound("Subscription not found")
        customer = await self.repository.customer(organization_id)
        assert customer is not None
        await self.repository.lock_customer(customer.id)
        return await self._save(customer, await self._provider.cancel(subscription.provider_id))

    async def _save(self, customer: Customer, external: ProviderSubscription) -> Subscription:
        if external.customer_provider_id != customer.provider_id:
            raise ValidationError("Provider customer mismatch")
        existing = await self.repository.subscription_by_provider(external.provider_id)
        subscription = Subscription(
            existing.id if existing else self._ids.new(),
            customer.organization_id,
            customer.id,
            external.provider_id,
            external.state,
            self._clock.now(),
        )
        await self.repository.save_subscription(subscription)
        await self._events.publish(
            (ApplicationEvent("subscription.changed", subscription.id, subscription.updated_at),)
        )
        return subscription

    async def webhook(self, payload: bytes, signature: str) -> bool:
        event = self._provider.verify_webhook(payload, signature)
        if not await self.repository.claim_event(self._provider.name, event.provider_event_id):
            return False
        if event.subscription_provider_id:
            external = await self._provider.subscription(event.subscription_provider_id)
            customer = await self.repository.customer_by_provider(external.customer_provider_id)
            if customer is None:
                # Roll back the event claim so provider retries can observe the committed customer.
                raise NotFound("Billing customer is not ready")
            await self.repository.lock_customer(customer.id)
            # Fetch under the lock: old webhook snapshots cannot overwrite newer state.
            await self._save(
                customer, await self._provider.subscription(event.subscription_provider_id)
            )
        return True

    async def sync_subscriptions(self) -> None:
        for subscription in await self.repository.subscriptions():
            customer = await self.repository.customer(subscription.organization_id)
            if customer:
                await self.repository.lock_customer(customer.id)
                await self._save(
                    customer, await self._provider.subscription(subscription.provider_id)
                )


__all__ = (
    "BillingRepository",
    "BillingService",
    "CheckoutSession",
    "Customer",
    "InvoiceReference",
    "PaymentEvent",
    "PaymentProvider",
    "Price",
    "Product",
    "ProviderSubscription",
    "Subscription",
    "SubscriptionState",
)
