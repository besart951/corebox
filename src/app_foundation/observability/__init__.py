import copy
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, override
from uuid import UUID

from app_foundation.primitives import Metadata, OrganizationId, UserId

request_id: ContextVar[str] = ContextVar("foundation_request_id", default="")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: UUID
    action: str
    occurred_at: datetime
    actor_id: UserId | None
    organization_id: OrganizationId | None
    entity_id: UUID
    metadata: Metadata = ()


class AuditSink(Protocol):
    async def append(self, record: AuditRecord) -> None: ...


class Metrics(Protocol):
    def increment(self, name: str, labels: Metadata = ()) -> None: ...
    def observe(self, name: str, value: float, labels: Metadata = ()) -> None: ...


class Tracing(Protocol):
    def record(self, operation: str, duration_seconds: float, correlation_id: str) -> None: ...


class MemoryAuditSink:
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    async def append(self, record: AuditRecord) -> None:
        self._records.append(record)


class ContextFilter(logging.Filter):
    """Return a copy so redaction does not alter another handler's input."""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    @override
    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        result = copy.copy(record)
        message = result.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "[REDACTED]")
        message = re.sub(
            r"(?i)(authorization)\s*[=:]\s*(?:Bearer|Basic)\s+[^\s,;]+",
            r"\1=[REDACTED]",
            message,
        )
        message = re.sub(
            r"(?i)(authorization|password|secret|token|recovery_code)\s*[=:]\s*[^\s,;]+",
            r"\1=[REDACTED]",
            message,
        )
        result.msg = f"[{request_id.get()}] {message}"
        result.args = ()
        result.exc_info = None
        result.exc_text = None
        result.stack_info = None
        return result


__all__ = (
    "AuditRecord",
    "AuditSink",
    "ContextFilter",
    "MemoryAuditSink",
    "Metrics",
    "Tracing",
    "request_id",
)
