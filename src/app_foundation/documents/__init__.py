from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app_foundation.primitives import Clock, IdGenerator


@dataclass(frozen=True, slots=True)
class DocumentTemplate:
    name: str
    source: str
    content_type: str = "text/html"


@dataclass(frozen=True, slots=True)
class DocumentContext:
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class GeneratedDocument:
    id: UUID
    storage_key: str
    content_type: str
    created_at: datetime
    size_bytes: int


class DocumentRenderer(Protocol):
    async def render(self, template: DocumentTemplate, context: DocumentContext) -> bytes: ...


class DocumentStorage(Protocol):
    async def put(self, key: str, content: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...


class DocumentService:
    def __init__(
        self, renderer: DocumentRenderer, storage: DocumentStorage, ids: IdGenerator, clock: Clock
    ) -> None:
        self._renderer = renderer
        self._storage = storage
        self._ids = ids
        self._clock = clock

    async def generate(
        self, template: DocumentTemplate, context: DocumentContext
    ) -> GeneratedDocument:
        content = await self._renderer.render(template, context)
        identifier = self._ids.new()
        key = str(identifier)
        await self._storage.put(key, content)
        return GeneratedDocument(
            identifier, key, template.content_type, self._clock.now(), len(content)
        )


class MemoryDocumentStorage:
    def __init__(self) -> None:
        self._documents: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes) -> None:
        self._documents[key] = content

    async def get(self, key: str) -> bytes:
        return self._documents[key]


__all__ = (
    "DocumentContext",
    "DocumentRenderer",
    "DocumentService",
    "DocumentStorage",
    "DocumentTemplate",
    "GeneratedDocument",
    "MemoryDocumentStorage",
)
