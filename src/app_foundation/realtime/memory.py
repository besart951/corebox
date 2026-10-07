import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app_foundation.primitives import InfrastructureUnavailable
from app_foundation.realtime import RealtimeEvent, Topic


class MemoryRealtimeBroker:
    """Bounded single-process delivery; slow subscribers disconnect."""

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        self._subscribers: dict[Topic, set[asyncio.Queue[RealtimeEvent | None]]] = {}

    async def publish(self, event: RealtimeEvent) -> None:
        for queue in tuple(self._subscribers.get(event.topic, ())):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self._subscribers[event.topic].discard(queue)
            else:
                queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, topic: Topic) -> AsyncIterator[AsyncIterator[RealtimeEvent]]:
        queue: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue(self._capacity)
        self._subscribers.setdefault(topic, set()).add(queue)

        async def stream() -> AsyncIterator[RealtimeEvent]:
            while True:
                event = await queue.get()
                if event is None:
                    raise InfrastructureUnavailable(
                        "Realtime subscriber fell behind; reconnect and reload"
                    )
                yield event

        try:
            yield stream()
        finally:
            subscribers = self._subscribers.get(topic)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(topic, None)
