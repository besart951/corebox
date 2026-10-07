import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid7

import pytest

from app_foundation.access_control import Authorizer, Principal, Resource, Role, RoleAssignment
from app_foundation.access_control.memory import MemoryRoleRepository
from app_foundation.addresses import Address, CountryCode, PostalAddress
from app_foundation.billing import BillingService, PaymentEvent, SubscriptionState
from app_foundation.billing.memory import FakePaymentProvider, MemoryBillingRepository
from app_foundation.communication.email import EmailAddress, MemoryEmailSender
from app_foundation.documents import DocumentContext, DocumentService, DocumentTemplate
from app_foundation.documents.adapters import FileDocumentStorage, HtmlDocumentRenderer
from app_foundation.events import InProcessEventPublisher
from app_foundation.jobs import CronSchedule, FunctionJob, JobRegistry, JobRunner, MemoryLock
from app_foundation.localization import CatalogTranslator, TranslationCatalog
from app_foundation.notification import (
    NotificationChannel,
    NotificationPreference,
    NotificationRecipient,
    NotificationService,
)
from app_foundation.notification.memory import MemoryNotificationRepository
from app_foundation.notification.transports import CommunicationTransport
from app_foundation.organization import MembershipRole, OrganizationService
from app_foundation.organization.memory import MemoryOrganizationRepository
from app_foundation.primitives import (
    FixedClock,
    NotFound,
    OrganizationId,
    PageRequest,
    PermissionDenied,
    UserId,
    UUID7Generator,
    ValidationError,
)
from app_foundation.realtime import RealtimeEvent
from app_foundation.realtime.memory import MemoryRealtimeBroker
from app_foundation.scheduling import Recurrence, Reminder, ReminderService
from app_foundation.scheduling.memory import MemoryReminderRepository

CLOCK = FixedClock(datetime(2026, 3, 28, 8, tzinfo=UTC))


async def test_organization_rbac_tenant_isolation_and_invitation_reuse() -> None:
    repository = MemoryOrganizationRepository()
    service = OrganizationService(repository, CLOCK, UUID7Generator(), InProcessEventPublisher())
    user, other = UserId(uuid7()), UserId(uuid7())
    first = await service.create("First", user)
    second = await service.create("Second", other)
    roles = MemoryRoleRepository()
    await roles.save_role(Role("reader", frozenset({"custom.read"})))
    await roles.assign(RoleAssignment(user, "reader", first.id))
    auth = Authorizer(roles, repository)
    await auth.require(Principal(user), "custom.read", Resource(first.id))
    with pytest.raises(PermissionDenied):
        await auth.require(Principal(user), "custom.read", Resource(second.id))
    _, raw = await service.invite(first.id, "new@example.com", MembershipRole.MEMBER)
    await service.accept_invitation(raw, other, "new@example.com")
    with pytest.raises(ValidationError):
        await service.accept_invitation(raw, other, "new@example.com")
    team = await service.create_team(second.id, "Other team")
    with pytest.raises(NotFound):
        await service.add_member(first.id, user, MembershipRole.MEMBER, team.id)


async def test_notification_preferences_delivery_and_ownership() -> None:
    repository = MemoryNotificationRepository()
    service = NotificationService(repository, CLOCK, UUID7Generator(), InProcessEventPublisher())
    user, org = UserId(uuid7()), OrganizationId(uuid7())
    await repository.save_preference(NotificationPreference(user, NotificationChannel.EMAIL, False))
    first = await service.create(
        org,
        NotificationRecipient(user, "person@example.com"),
        "Hello",
        "Body",
        "test",
        (NotificationChannel.EMAIL,),
    )
    assert not repository.deliveries
    await repository.save_preference(NotificationPreference(user, NotificationChannel.EMAIL, True))
    await service.create(
        org,
        NotificationRecipient(user, "person@example.com"),
        "Hello",
        "Body",
        "test",
        (NotificationChannel.EMAIL,),
    )
    sender = MemoryEmailSender()
    await service.deliver_pending(
        CommunicationTransport(EmailAddress("sender@example.com"), sender)
    )
    await service.deliver_pending(
        CommunicationTransport(EmailAddress("sender@example.com"), sender)
    )
    assert len(sender.messages) == 1
    with pytest.raises(NotFound):
        await service.mark_read(org, UserId(uuid7()), first.id)
    await service.mark_read(org, user)
    assert all(n.read_at for n in await repository.list(org, user, PageRequest()))


async def test_billing_idempotency_and_current_provider_state() -> None:
    repository, provider = MemoryBillingRepository(), FakePaymentProvider()
    service = BillingService(
        repository, provider, UUID7Generator(), CLOCK, InProcessEventPublisher()
    )
    org = OrganizationId(uuid7())
    customer = await service.create_customer(org, "billing@example.com")
    assert await service.create_customer(org, "billing@example.com") == customer
    subscription = await service.subscribe(org, "price", uuid7())
    provider.items[subscription.provider_id] = replace(
        provider.items[subscription.provider_id], state=SubscriptionState.CANCELED
    )
    provider.events[b"old"] = PaymentEvent(
        "event1", "subscription.updated", subscription.provider_id
    )
    assert await service.webhook(b"old", "fake-valid-signature")
    assert not await service.webhook(b"old", "fake-valid-signature")
    stored = await repository.subscription(org, subscription.id)
    assert stored and stored.state == SubscriptionState.CANCELED
    with pytest.raises(NotFound):
        await service.cancel(OrganizationId(uuid7()), subscription.id)


async def test_jobs_do_not_overlap_and_release_lock_after_failure() -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def action() -> None:
        started.set()
        await release.wait()

    runner = JobRunner(JobRegistry((FunctionJob("test", action),)), MemoryLock())
    task = asyncio.create_task(runner.run("test"))
    await started.wait()
    assert not await runner.run("test")
    release.set()
    assert await task
    assert await runner.run("test")
    assert CronSchedule("0 9 * * *", "Europe/Zurich").next_after(CLOCK.now()) > CLOCK.now()


async def test_realtime_subscriptions_cleanup() -> None:
    broker = MemoryRealtimeBroker()
    event = RealtimeEvent(uuid7(), "topic", "created", CLOCK.now())
    async with broker.subscribe("topic") as stream:
        await broker.publish(event)
        assert await anext(stream) == event
    await broker.publish(event)


async def test_document_escaping_and_traversal(tmp_path: Path) -> None:
    storage = FileDocumentStorage(tmp_path)
    service = DocumentService(HtmlDocumentRenderer(), storage, UUID7Generator(), CLOCK)
    document = await service.generate(
        DocumentTemplate("welcome", "<h1>{{ name }}</h1>"), DocumentContext((("name", "<script>"),))
    )
    assert await storage.get(document.storage_key) == b"<h1>&lt;script&gt;</h1>"
    with pytest.raises(ValidationError):
        await storage.put("../escape", b"bad")


class RecordingTrigger:
    def __init__(self) -> None:
        self.reminders: list[Reminder] = []

    async def trigger(self, reminder: Reminder) -> None:
        self.reminders.append(reminder)


async def test_reminder_daily_wall_time_across_dst() -> None:
    repository, trigger = MemoryReminderRepository(), RecordingTrigger()
    service = ReminderService(repository, trigger, CLOCK, UUID7Generator())
    reminder = await service.create(
        OrganizationId(uuid7()), "Daily", CLOCK.now(), "Europe/Zurich", recurrence=Recurrence.DAILY
    )
    await service.trigger_due()
    stored = await repository.get(reminder.organization_id, reminder.id)
    assert stored and stored.due_at == CLOCK.now() + timedelta(hours=23)
    await service.trigger_due()
    assert len(trigger.reminders) == 1


def test_localization_and_address_validation() -> None:
    translator = CatalogTranslator(
        (
            TranslationCatalog("en", (("hello", "Hello {name}"),)),
            TranslationCatalog("de", (("hello", "Hallo {name}"),)),
        )
    )
    assert translator.translate("hello", "de-CH", (("name", "Ada"),)) == "Hallo Ada"
    assert translator.translate("hello", "fr", (("name", "Ada"),)) == "Hello Ada"
    assert translator.translate("missing", "fr") == "missing"
    with pytest.raises(ValidationError):
        Address(PostalAddress("Street", "8000", "Zurich", CountryCode("CH")), 95, 1)
