from dataclasses import dataclass
from typing import Protocol

from app_foundation.primitives import ValidationError

type Locale = str
type TranslationKey = str


class Translator(Protocol):
    def translate(
        self, key: TranslationKey, locale: Locale, parameters: tuple[tuple[str, str], ...] = ()
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class TranslationCatalog:
    locale: Locale
    entries: tuple[tuple[TranslationKey, str], ...]


class CatalogTranslator:
    def __init__(
        self, catalogs: tuple[TranslationCatalog, ...], default_locale: Locale = "en"
    ) -> None:
        self._catalogs = {
            catalog.locale.replace("_", "-").lower(): dict(catalog.entries) for catalog in catalogs
        }
        self._default = default_locale.replace("_", "-").lower()

    def translate(
        self, key: TranslationKey, locale: Locale, parameters: tuple[tuple[str, str], ...] = ()
    ) -> str:
        normalized = locale.replace("_", "-").lower()
        for candidate in dict.fromkeys((normalized, normalized.split("-")[0], self._default)):
            template = self._catalogs.get(candidate, {}).get(key)
            if template is not None:
                try:
                    return template.format_map(dict(parameters))
                except (KeyError, ValueError) as error:
                    raise ValidationError(
                        "Translation parameters are missing or invalid"
                    ) from error
        return key


__all__ = ("CatalogTranslator", "Locale", "TranslationCatalog", "TranslationKey", "Translator")
