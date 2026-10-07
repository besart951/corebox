"""Immutable events and an explicitly assembled in-process publisher."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app_foundation.primitives import Metadata


class Event(Protocol):
    @property
    def event_name(self) -> str: ...


class EventPublisher(Protocol):
    async def publish(self, events: tuple[Event, ...]) -> None: ...


type EventHandler = Callable[[Event], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    event_name: str
    entity_id: UUID
    occurred_at: datetime
    metadata: Metadata = ()


class InProcessEventPublisher:
    def __init__(self, handlers: tuple[EventHandler, ...] = ()) -> None:
        self._handlers = handlers

    async def publish(self, events: tuple[Event, ...]) -> None:
        for event in events:
            for handler in self._handlers:
                await handler(event)


__all__ = ("ApplicationEvent", "Event", "EventHandler", "EventPublisher", "InProcessEventPublisher")
