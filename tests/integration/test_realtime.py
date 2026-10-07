from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app_foundation.api import install_exception_handlers
from app_foundation.primitives import PermissionDenied
from app_foundation.realtime import RealtimeEvent
from app_foundation.realtime.memory import MemoryRealtimeBroker
from app_foundation.realtime.sse import create_sse_router
from app_foundation.realtime.websocket import create_websocket_router


async def authorize(header: str, topic: str) -> None:
    if header != "Bearer test-token" or topic != "owned-topic":
        raise PermissionDenied("Access denied")


class FiniteSubscription:
    @asynccontextmanager
    async def subscribe(self, topic: str) -> AsyncIterator[AsyncIterator[RealtimeEvent]]:
        async def events() -> AsyncIterator[RealtimeEvent]:
            yield RealtimeEvent(uuid7(), topic, "created", datetime(2026, 1, 1, tzinfo=UTC))

        yield events()


async def test_sse_authorization_and_wire_format() -> None:
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(create_sse_router(FiniteSubscription(), authorize))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/events/other", headers={"Authorization": "Bearer test-token"})
        assert denied.status_code == 403
        response = await client.get(
            "/events/owned-topic", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"type": "created"' in response.text
        assert response.text.endswith("\n\n")


def test_websocket_access_and_memory_broker_delivery() -> None:
    broker = MemoryRealtimeBroker()
    app = FastAPI()
    app.include_router(create_websocket_router(broker, authorize))

    @app.post("/publish")
    async def publish() -> None:
        await broker.publish(
            RealtimeEvent(uuid7(), "owned-topic", "created", datetime(2026, 1, 1, tzinfo=UTC))
        )

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/other"):
            pass
        with client.websocket_connect(
            "/ws/owned-topic", headers={"Authorization": "Bearer test-token"}
        ) as websocket:
            assert client.post("/publish").status_code == 200
            assert websocket.receive_json()["type"] == "created"
