"""Locale matching. Hand-written so Babel stays a dev-only dependency."""

from __future__ import annotations

from collections.abc import Sequence

from polyadmin.i18n.translator import PSEUDO_LOCALE


def parse_accept_language(header: str | None) -> list[str]:
    """Language ranges ordered by q, highest first; q=0 and "*" dropped."""
    ranked = []
    for position, part in enumerate((header or "").split(",")):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip()
        q = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        if tag and tag != "*" and q > 0:
            ranked.append((-q, position, tag))
    return [tag for _, _, tag in sorted(ranked)]


def match_locale(supported: Sequence[str], candidate: str | None) -> str | None:
    """The supported locale a candidate names, or None.

    Exact matches win (case-insensitively, "_" or "-"); otherwise a
    regional variant maps onto its base language (fr-CA -> fr). The
    pseudo-locale matches only exactly.
    """
    if not candidate:
        return None
    wanted = candidate.strip().replace("_", "-").lower()
    by_lower = {locale.lower(): locale for locale in supported}
    if wanted in by_lower:
        return by_lower[wanted]
    base = wanted.split("-")[0]
    match = by_lower.get(base)
    return match if match and match != PSEUDO_LOCALE else None


def match_accept_language(supported: Sequence[str], header: str | None) -> str | None:
    """The best supported locale for an Accept-Language header, or None.
    Ranges are tried one at a time in q order."""
    for tag in parse_accept_language(header):
        if tag.lower() == PSEUDO_LOCALE.lower():
            continue
        match = match_locale(supported, tag)
        if match:
            return match
    return None
