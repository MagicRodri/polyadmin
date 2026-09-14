"""The request's locale, for code that has no request to hand.

Set per request by the FastAPI adapter's route class; action handlers,
validators and ModelAdmin methods read it through these helpers.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from polyadmin.i18n.translator import DEFAULT_LOCALE, Translator


@dataclass(frozen=True)
class LocaleContext:
    locale: str
    translator: Translator


_current: ContextVar[LocaleContext | None] = ContextVar("polyadmin_locale", default=None)


def get_locale() -> str:
    current = _current.get()
    return current.locale if current else DEFAULT_LOCALE


def gettext(message: str) -> str:
    current = _current.get()
    return current.translator.gettext(current.locale, message) if current else message


def ngettext(singular: str, plural: str, n: int) -> str:
    current = _current.get()
    if current is None:
        return singular if n == 1 else plural
    return current.translator.ngettext(current.locale, singular, plural, n)


def N_(message: str) -> str:
    """Mark a string for extraction without translating it."""
    return message


@contextmanager
def use_locale(locale: str, translator: Translator) -> Iterator[None]:
    token = _current.set(LocaleContext(locale, translator))
    try:
        yield
    finally:
        _current.reset(token)
