from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app_foundation.primitives import Metadata, UserId, ValidationError


def normalize_email(email: str) -> str:
    value = email.strip().casefold()
    if len(value) > 254 or value.count("@") != 1 or any(c.isspace() for c in value):
        raise ValidationError("Invalid email address")
    local, domain = value.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValidationError("Invalid email address")
    return value


@dataclass(frozen=True, slots=True)
class User:
    id: UserId
    email: str
    display_name: str
    created_at: datetime
    updated_at: datetime
    first_name: str = ""
    last_name: str = ""
    preferred_locale: str = "en"
    timezone: str = "UTC"
    active: bool = True
    metadata: Metadata = ()

    def __post_init__(self) -> None:
        if self.email != normalize_email(self.email):
            raise ValidationError("Email must be normalized")
        if not self.display_name.strip():
            raise ValidationError("Display name is required")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValidationError("Unknown timezone") from error
