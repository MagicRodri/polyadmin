"""Slugification for prepopulated_fields (docs/model-admin.md).

Mirrors the client-side rule, so what the browser filled in and what a
script here produces agree.
"""

from __future__ import annotations

import re
import unicodedata

# The Russian alphabet in the BGN/PCGN-flavoured romanisation most readable
# to a Latin-alphabet reader. Keyed on the lowercase letter; transliterate
# lowercases before looking up, so one entry per letter serves both cases.
CYRILLIC_ASCII = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip

_NON_SLUG = re.compile(r"[^\w]+", re.UNICODE)


def slugify(value: str) -> str:
    """A URL-safe ASCII slug: "Café du Coin" becomes "cafe-du-coin" and
    "Привет мир" becomes "privet-mir".

    Letters outside the transliteration table drop out, so a title written
    wholly in one -- CJK, say -- slugifies to "". `slugify_unicode` is the
    way out for an application that wants those letters kept.
    """
    return _slugify(_transliterate(value))


def slugify_unicode(value: str) -> str:
    """slugify without the ASCII step: punctuation and spacing are still
    normalised, but the letters are kept as they are."""
    return _slugify(value)


def _slugify(value: str) -> str:
    """Lowercase, collapse every run of non-alphanumerics into one hyphen,
    and trim the hyphens from both ends."""
    # \w keeps the underscore, which is not slug punctuation here.
    return _NON_SLUG.sub("-", value.lower().replace("_", "-")).strip("-")


def _transliterate(value: str) -> str:
    """Map the letters PolyAdmin ships locales for onto ASCII: Cyrillic
    through the table above, Latin-1's accents by decomposing and dropping
    the combining marks. Anything left non-ASCII is dropped."""
    mapped = "".join(CYRILLIC_ASCII.get(ch.lower(), ch) for ch in value)
    decomposed = unicodedata.normalize("NFD", mapped)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in without_marks if ch.isascii())
