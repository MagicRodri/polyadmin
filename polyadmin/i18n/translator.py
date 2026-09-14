"""The Translator: framework and host strings, keyed by the English text."""

from __future__ import annotations

import gettext as _stdlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

DEFAULT_LOCALE = "en"
PSEUDO_LOCALE = "en-XA"
DOMAIN = "polyadmin"
FRAMEWORK_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"


class Translator(Protocol):
    def gettext(self, locale: str, message: str) -> str: ...
    def ngettext(self, locale: str, singular: str, plural: str, n: int) -> str: ...


def _catalog_locales(localedir: Path, domain: str) -> set[str]:
    if not localedir.is_dir():
        return set()
    return {
        entry.name.replace("_", "-")
        for entry in localedir.iterdir()
        if (entry / "LC_MESSAGES" / f"{domain}.mo").is_file()
    }


class GettextTranslator:
    """The default Translator: gettext catalogs, host ahead of framework.

    `catalogs` are (localedir, domain) pairs, consulted in order before the
    framework's own, so a host can translate its strings and reword ours.
    """

    def __init__(self, catalogs: Iterable[tuple[str | Path, str]] = ()) -> None:
        sources = [(Path(localedir), domain) for localedir, domain in catalogs]
        sources.append((FRAMEWORK_LOCALE_DIR, DOMAIN))
        found = {DEFAULT_LOCALE}
        for localedir, domain in sources:
            found |= _catalog_locales(localedir, domain)
        self._locales = [DEFAULT_LOCALE, *sorted(found - {DEFAULT_LOCALE})]
        self._chains: dict[str, _stdlib.NullTranslations] = {}
        for locale in self._locales:
            chain = None
            for localedir, domain in sources:
                translation = _stdlib.translation(
                    domain, localedir=localedir, languages=[locale.replace("-", "_")], fallback=True
                )
                if chain is None:
                    chain = translation
                else:
                    chain.add_fallback(translation)
            self._chains[locale] = chain

    def locales(self) -> list[str]:
        return list(self._locales)

    def gettext(self, locale: str, message: str) -> str:
        chain = self._chains.get(locale)
        # gettext("") returns the catalog's header block.
        if chain is None or not message:
            return message
        return chain.gettext(message)

    def ngettext(self, locale: str, singular: str, plural: str, n: int) -> str:
        chain = self._chains.get(locale)
        if chain is None:
            return singular if n == 1 else plural
        return chain.ngettext(singular, plural, n)


_PLACEHOLDER = re.compile(r"%(\([^)]*\))?[-+# 0]*\d*(\.\d+)?[a-zA-Z%]")
_ACCENTS = str.maketrans("aeiouycnszAEIOUYCNSZ", "àéîöüýçñšžÀÉÎÖÜÝÇÑŠŽ")


def pseudo(text: str) -> str:
    """Accent a string's letters and bracket it -- "Save" becomes "[Šàvé]" --
    leaving %-placeholders intact so the result still formats."""
    out, last = ["["], 0
    for match in _PLACEHOLDER.finditer(text):
        out.append(text[last : match.start()].translate(_ACCENTS))
        out.append(match.group())
        last = match.end()
    out.append(text[last:].translate(_ACCENTS))
    out.append("]")
    return "".join(out)


def _is_pseudo(text: str) -> bool:
    """Whether text already looks like pseudo()'s output -- bracketed
    top to bottom, not merely containing a bracketed run somewhere."""
    return len(text) >= 2 and text.startswith("[") and text.endswith("]")


class PseudoTranslator:
    """Wraps another Translator, rewriting PSEUDO_LOCALE only."""

    def __init__(self, inner: Translator) -> None:
        self._inner = inner

    def gettext(self, locale: str, message: str) -> str:
        if locale != PSEUDO_LOCALE:
            return self._inner.gettext(locale, message)
        if _is_pseudo(message):
            # Already pseudo-translated -- an adapter re-translating a
            # host string returned from code (an action's message
            # becoming a flash, a rendered validation error). Wrapping
            # it again would double-bracket it.
            return message
        return pseudo(self._inner.gettext(DEFAULT_LOCALE, message)) if message else message

    def ngettext(self, locale: str, singular: str, plural: str, n: int) -> str:
        if locale != PSEUDO_LOCALE:
            return self._inner.ngettext(locale, singular, plural, n)
        if _is_pseudo(singular):
            return singular
        return pseudo(self._inner.ngettext(DEFAULT_LOCALE, singular, plural, n))
