"""Small shared vocabulary; no infrastructure dependencies."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NewType, Protocol
from uuid import UUID, uuid7

UserId = NewType("UserId", UUID)
OrganizationId = NewType("OrganizationId", UUID)
TeamId = NewType("TeamId", UUID)
MembershipId = NewType("MembershipId", UUID)
type Metadata = tuple[tuple[str, str], ...]


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    instant: datetime

    def __post_init__(self) -> None:
        require_aware(self.instant)

    def now(self) -> datetime:
        return self.instant


class IdGenerator(Protocol):
    def new(self) -> UUID: ...


class UUID7Generator:
    def new(self) -> UUID:
        return uuid7()


class FoundationError(Exception):
    """Base for errors callers can handle without importing an adapter."""


class NotFound(FoundationError):
    pass


class Conflict(FoundationError):
    pass


class ValidationError(FoundationError):
    pass


class PermissionDenied(FoundationError):
    pass


class InfrastructureUnavailable(FoundationError):
    pass


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("A timezone-aware datetime is required")


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100 or self.offset < 0:
            raise ValidationError("Page limit must be 1..100 and offset nonnegative")


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    total: int


@dataclass(frozen=True, slots=True)
class Branding:
    name: str
    logo_url: str | None = None
    primary_color: str = "#1f2937"
    metadata: Metadata = field(default_factory=tuple)
