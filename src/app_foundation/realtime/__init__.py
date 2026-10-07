from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app_foundation.primitives import Metadata

type Topic = str


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    id: UUID
    topic: Topic
    event_name: str
    created_at: datetime
    data: Metadata = ()


class RealtimePublisher(Protocol):
    async def publish(self, event: RealtimeEvent) -> None: ...


class Subscription(Protocol):
    def subscribe(
        self, topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[RealtimeEvent]]: ...


__all__ = ("RealtimeEvent", "RealtimePublisher", "Subscription", "Topic")
