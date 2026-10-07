from dataclasses import dataclass
from typing import Protocol

from app_foundation.primitives import ValidationError


@dataclass(frozen=True, slots=True)
class CountryCode:
    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) != 2
            or not self.value.isascii()
            or not self.value.isalpha()
            or not self.value.isupper()
        ):
            raise ValidationError("Country code must be two uppercase ASCII letters")


@dataclass(frozen=True, slots=True)
class PostalAddress:
    street: str
    postal_code: str
    city: str
    country: CountryCode
    house_number: str = ""
    additional_line: str = ""
    region: str = ""
    person: str = ""
    organization: str = ""

    def __post_init__(self) -> None:
        if not self.city.strip():
            raise ValidationError("City is required")


@dataclass(frozen=True, slots=True)
class Address:
    postal: PostalAddress
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Supply both coordinates")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValidationError("Invalid latitude")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValidationError("Invalid longitude")


class AddressNormalizer(Protocol):
    async def normalize(self, address: PostalAddress) -> PostalAddress: ...


class AddressValidator(Protocol):
    async def validate(self, address: PostalAddress) -> tuple[str, ...]: ...


__all__ = ("Address", "AddressNormalizer", "AddressValidator", "CountryCode", "PostalAddress")
