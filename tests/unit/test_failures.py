import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from app_foundation.events import InProcessEventPublisher
from app_foundation.notification import (
    Delivery,
    NotificationChannel,
    NotificationRecipient,
    NotificationService,
)
from app_foundation.notification.memory import MemoryNotificationRepository
from app_foundation.observability import ContextFilter
from app_foundation.primitives import (
    FixedClock,
    InfrastructureUnavailable,
    OrganizationId,
    UserId,
    UUID7Generator,
)
from app_foundation.realtime import RealtimeEvent
from app_foundation.realtime.memory import MemoryRealtimeBroker


class UnavailableTransport:
    def __init__(self) -> None:
        self.calls: int = 0

    async def deliver(self, delivery: Delivery) -> None:
        assert delivery.channel == NotificationChannel.EMAIL
        self.calls += 1
        raise InfrastructureUnavailable("sensitive provider details must not be stored")


async def test_delivery_retries_are_bounded_and_errors_are_redacted() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    repository = MemoryNotificationRepository()
    transport = UnavailableTransport()
    service = NotificationService(
        repository, FixedClock(now), UUID7Generator(), InProcessEventPublisher()
    )
    await service.create(
        OrganizationId(uuid7()),
        NotificationRecipient(UserId(uuid7()), "person@example.com"),
        "Subject",
        "Body",
        "test",
        (NotificationChannel.EMAIL,),
    )
    for day in range(7):
        service = NotificationService(
            repository,
            FixedClock(now + timedelta(days=day)),
            UUID7Generator(),
            InProcessEventPublisher(),
        )
        await service.deliver_pending(transport)
    assert transport.calls == 5
    assert next(iter(repository.deliveries.values())).last_error == "InfrastructureUnavailable"


async def test_slow_realtime_subscriber_disconnects() -> None:
    broker = MemoryRealtimeBroker(capacity=1)
    event = RealtimeEvent(uuid7(), "topic", "created", datetime(2026, 1, 1, tzinfo=UTC))
    async with broker.subscribe("topic") as stream:
        await broker.publish(event)
        await broker.publish(event)
        with pytest.raises(InfrastructureUnavailable):
            await anext(stream)


def test_logging_redacts_secrets_without_mutating_input() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Authorization: Bearer opaque-secret password=pass api=private-key",
        (),
        None,
    )
    redacted = ContextFilter(("private-key",)).filter(record)
    message = redacted.getMessage()
    assert "opaque-secret" not in message
    assert "password=pass" not in message
    assert "private-key" not in message
    assert "private-key" in record.getMessage()
