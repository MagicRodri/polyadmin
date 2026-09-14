"""I18n: an Admin's internationalisation setup, built once at mount."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from polyadmin.i18n.negotiation import match_accept_language, match_locale
from polyadmin.i18n.translator import (
    DEFAULT_LOCALE,
    PSEUDO_LOCALE,
    GettextTranslator,
    PseudoTranslator,
    Translator,
)

BUILTIN_LOCALE_NAMES = {
    "en": "English",
    "fr": "Français",
    "ru": "Русский",
    PSEUDO_LOCALE: "Pseudo (en-XA)",
}


@dataclass(frozen=True)
class LocaleOption:
    code: str
    name: str


class I18n:
    def __init__(self, *, translator: Translator, default: str, supported: Sequence[str], names: Mapping[str, str]) -> None:
        self.translator = translator
        self.default = default
        self.supported = list(supported)
        self._names = {**BUILTIN_LOCALE_NAMES, **names}

    @classmethod
    def from_admin(cls, admin: Any) -> I18n:
        default = admin.default_locale or DEFAULT_LOCALE
        translator = admin.translator
        available = [DEFAULT_LOCALE]
        if translator is None:
            translator = GettextTranslator(admin.catalogs)
            available = translator.locales()
        supported = available
        if admin.locales:
            if admin.translator is None:
                missing = [locale for locale in admin.locales if locale not in available]
                if missing:
                    raise ValueError(f"polyadmin: locale {missing[0]!r} has no catalog")
            supported = list(admin.locales)
        if default not in supported:
            raise ValueError(f"polyadmin: default locale {default!r} is not among the supported locales {supported}")
        if admin.pseudo_locale:
            supported = [*supported, PSEUDO_LOCALE]
            translator = PseudoTranslator(translator)
        return cls(translator=translator, default=default, supported=supported, names=admin.locale_names or {})

    def match(self, candidate: str | None) -> str | None:
        return match_locale(self.supported, candidate)

    def resolve(self, cookie: str | None, resolver: Callable[[], str | None] | None, accept_language: str | None) -> str:
        """Cookie, then the host's resolver, then Accept-Language, then the
        default. `resolver` is a thunk so a cookie that decides never costs
        an authentication."""
        locale = self.match(cookie)
        if locale:
            return locale
        if resolver is not None:
            locale = self.match(resolver())
            if locale:
                return locale
        return match_accept_language(self.supported, accept_language) or self.default

    def name(self, code: str) -> str:
        return self._names.get(code) or code

    def options(self) -> list[LocaleOption]:
        return [LocaleOption(code, self.name(code)) for code in self.supported]
