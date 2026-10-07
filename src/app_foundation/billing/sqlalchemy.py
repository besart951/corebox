from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedColumn

from app_foundation.billing import Customer, Subscription, SubscriptionState
from app_foundation.persistence import Base, translate_errors
from app_foundation.primitives import OrganizationId


class CustomerRecord(Base):
    __tablename__ = "af_billing_customers"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_organizations.id"), unique=True
    )
    email: Mapped[str]
    provider_id: Mapped[str] = MappedColumn[str](unique=True)


class SubscriptionRecord(Base):
    __tablename__ = "af_subscriptions"
    id: Mapped[UUID] = MappedColumn[UUID](primary_key=True)
    organization_id: Mapped[UUID] = MappedColumn[UUID](
        ForeignKey("af_organizations.id"), index=True
    )
    customer_id: Mapped[UUID] = MappedColumn[UUID](ForeignKey("af_billing_customers.id"))
    provider_id: Mapped[str] = MappedColumn[str](unique=True)
    state: Mapped[str]
    updated_at: Mapped[datetime] = MappedColumn[datetime](DateTime(timezone=True))


class PaymentEventRecord(Base):
    __tablename__ = "af_payment_events"
    provider: Mapped[str] = MappedColumn[str](primary_key=True)
    event_id: Mapped[str] = MappedColumn[str](primary_key=True)


def _customer(r: CustomerRecord) -> Customer:
    return Customer(r.id, OrganizationId(r.organization_id), r.email, r.provider_id)


def _subscription(r: SubscriptionRecord) -> Subscription:
    return Subscription(
        r.id,
        OrganizationId(r.organization_id),
        r.customer_id,
        r.provider_id,
        SubscriptionState(r.state),
        r.updated_at,
    )


class SqlAlchemyBillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_customer(self, customer: Customer) -> None:
        async with translate_errors():
            self._session.add(
                CustomerRecord(
                    id=customer.id,
                    organization_id=customer.organization_id,
                    email=customer.email,
                    provider_id=customer.provider_id,
                )
            )
            await self._session.flush()

    async def customer(self, organization_id: OrganizationId) -> Customer | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(CustomerRecord).where(CustomerRecord.organization_id == organization_id)
            )
            return _customer(r) if r else None

    async def customer_by_provider(self, provider_id: str) -> Customer | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(CustomerRecord).where(CustomerRecord.provider_id == provider_id)
            )
            return _customer(r) if r else None

    async def save_subscription(self, subscription: Subscription) -> None:
        async with translate_errors():
            await self._session.merge(
                SubscriptionRecord(
                    id=subscription.id,
                    organization_id=subscription.organization_id,
                    customer_id=subscription.customer_id,
                    provider_id=subscription.provider_id,
                    state=subscription.state.value,
                    updated_at=subscription.updated_at,
                )
            )
            await self._session.flush()

    async def subscription(
        self, organization_id: OrganizationId, subscription_id: UUID
    ) -> Subscription | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(SubscriptionRecord).where(
                    SubscriptionRecord.id == subscription_id,
                    SubscriptionRecord.organization_id == organization_id,
                )
            )
            return _subscription(r) if r else None

    async def subscription_by_provider(self, provider_id: str) -> Subscription | None:
        async with translate_errors():
            r = await self._session.scalar(
                select(SubscriptionRecord).where(SubscriptionRecord.provider_id == provider_id)
            )
            return _subscription(r) if r else None

    async def claim_event(self, provider: str, event_id: str) -> bool:
        async with translate_errors():
            result = await self._session.execute(
                insert(PaymentEventRecord)
                .values(provider=provider, event_id=event_id)
                .on_conflict_do_nothing()
                .returning(PaymentEventRecord.event_id)
            )
            return result.scalar_one_or_none() is not None

    async def lock_customer(self, customer_id: UUID) -> None:
        async with translate_errors():
            await self._session.scalar(
                select(CustomerRecord).where(CustomerRecord.id == customer_id).with_for_update()
            )

    async def subscriptions(self) -> tuple[Subscription, ...]:
        async with translate_errors():
            return tuple(
                _subscription(r) for r in await self._session.scalars(select(SubscriptionRecord))
            )
