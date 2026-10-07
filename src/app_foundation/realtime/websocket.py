import asyncio
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app_foundation.primitives import FoundationError
from app_foundation.realtime import Subscription
from app_foundation.realtime.sse import TopicAuthorization


def create_websocket_router(broker: Subscription, authorize: TopicAuthorization) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/{topic}")
    async def websocket(websocket: WebSocket, topic: str) -> None:
        authorization = websocket.headers.get("authorization", "")
        try:
            await authorize(authorization, topic)
        except FoundationError:
            await websocket.close(code=1008)
            return
        await websocket.accept()

        async def receive_disconnect() -> None:
            while True:
                await websocket.receive_text()

        async def send() -> None:
            async with broker.subscribe(topic) as events:
                async for event in events:
                    await authorize(authorization, topic)
                    await websocket.send_json(
                        {"id": str(event.id), "type": event.event_name, "data": dict(event.data)}
                    )

        tasks = (asyncio.create_task(send()), asyncio.create_task(receive_disconnect()))
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except WebSocketDisconnect, FoundationError:
            with suppress(RuntimeError):
                await websocket.close(code=1008)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return router
