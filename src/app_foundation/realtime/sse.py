import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Header
from starlette.responses import StreamingResponse

from app_foundation.realtime import Subscription

type TopicAuthorization = Callable[[str, str], Awaitable[None]]


def create_sse_router(broker: Subscription, authorize: TopicAuthorization) -> APIRouter:
    router = APIRouter()

    @router.get("/events/{topic}")
    async def events(topic: str, authorization: str = Header()) -> StreamingResponse:
        await authorize(authorization, topic)

        async def stream() -> AsyncIterator[str]:
            async with broker.subscribe(topic) as events:
                async for event in events:
                    # Recheck membership/session revocation on every delivered event.
                    await authorize(authorization, topic)
                    payload = json.dumps(
                        {"id": str(event.id), "type": event.event_name, "data": dict(event.data)}
                    )
                    yield f"data: {payload}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
