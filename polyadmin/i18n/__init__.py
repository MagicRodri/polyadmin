"""Internationalisation: the Translator, locale resolution, and the
helpers host code uses to translate its own strings. See docs/i18n.md."""

from polyadmin.i18n.context import (
    N_,
    LocaleContext,
    get_locale,
    gettext,
    ngettext,
    use_locale,
)
from polyadmin.i18n.negotiation import (
    match_accept_language,
    match_locale,
    parse_accept_language,
)
from polyadmin.i18n.setup import BUILTIN_LOCALE_NAMES, I18n, LocaleOption
from polyadmin.i18n.translator import (
    DEFAULT_LOCALE,
    DOMAIN,
    FRAMEWORK_LOCALE_DIR,
    PSEUDO_LOCALE,
    GettextTranslator,
    PseudoTranslator,
    Translator,
    pseudo,
)

__all__ = [
    "BUILTIN_LOCALE_NAMES",
    "DEFAULT_LOCALE",
    "DOMAIN",
    "FRAMEWORK_LOCALE_DIR",
    "N_",
    "PSEUDO_LOCALE",
    "GettextTranslator",
    "I18n",
    "LocaleContext",
    "LocaleOption",
    "PseudoTranslator",
    "Translator",
    "get_locale",
    "gettext",
    "match_accept_language",
    "match_locale",
    "ngettext",
    "parse_accept_language",
    "pseudo",
    "use_locale",
]
