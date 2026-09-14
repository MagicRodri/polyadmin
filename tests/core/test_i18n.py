import gettext as stdlib_gettext

import pytest

from polyadmin.core.admin import Admin
from polyadmin.i18n import (
    DEFAULT_LOCALE,
    N_,
    PSEUDO_LOCALE,
    GettextTranslator,
    I18n,
    LocaleOption,
    PseudoTranslator,
    get_locale,
    gettext,
    match_accept_language,
    match_locale,
    ngettext,
    parse_accept_language,
    pseudo,
    use_locale,
)


def write_catalog(root, locale, entries, *, domain="polyadmin", plural_forms=None):
    """Compile a tiny .mo with the stdlib-compatible layout, no Babel needed."""
    from tests.core.mo import write_mo

    target = root / locale / "LC_MESSAGES"
    target.mkdir(parents=True)
    write_mo(target / f"{domain}.mo", entries, plural_forms=plural_forms)
    return root


RU_PLURALS = "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"


def test_missing_translation_falls_back_to_english(tmp_path):
    tr = GettextTranslator([(write_catalog(tmp_path, "fr", {"Save": "Enregistrer"}), "polyadmin")])
    assert tr.gettext("fr", "Cancel") == "Cancel"
    assert tr.gettext("de", "Save") == "Save"
    assert tr.gettext("fr", "Save") == "Enregistrer"


def test_empty_msgid_is_not_the_catalog_header(tmp_path):
    tr = GettextTranslator([(write_catalog(tmp_path, "fr", {"Save": "Enregistrer"}), "polyadmin")])
    assert tr.gettext("fr", "") == ""


def test_host_catalog_overrides_later_ones(tmp_path):
    first = write_catalog(tmp_path / "a", "fr", {"Save": "Sauvegarder"}, domain="host")
    second = write_catalog(tmp_path / "b", "fr", {"Save": "Enregistrer"}, domain="other")
    tr = GettextTranslator([(first, "host"), (second, "other")])
    assert tr.gettext("fr", "Save") == "Sauvegarder"


def test_russian_plural_forms(tmp_path):
    root = write_catalog(
        tmp_path, "ru", {("%(num)d record", "%(num)d records"): ["%(num)d запись", "%(num)d записи", "%(num)d записей"]},
        plural_forms=RU_PLURALS,
    )
    tr = GettextTranslator([(root, "polyadmin")])
    for n, want in {1: "1 запись", 2: "2 записи", 5: "5 записей", 11: "11 записей", 21: "21 запись", 22: "22 записи"}.items():
        assert tr.ngettext("ru", "%(num)d record", "%(num)d records", n) % {"num": n} == want


def test_missing_plural_falls_back_to_english():
    tr = GettextTranslator()
    assert tr.ngettext("ru", "record", "records", 5) == "records"
    assert tr.ngettext("ru", "record", "records", 1) == "record"


def test_locales_lists_english_first_then_catalogs(tmp_path):
    write_catalog(tmp_path, "de", {"Save": "Speichern"})
    tr = GettextTranslator([(tmp_path, "polyadmin")])
    # Framework catalogs appear here once Task 14 ships them.
    assert tr.locales()[0] == "en"
    assert "de" in tr.locales()


def test_pseudo():
    assert pseudo("Save") == "[Šàvé]"
    assert pseudo("%(num)d users") % {"num": 3} == "[3 üšérš]"
    assert pseudo("100%% done") % {} == "[100% döñé]"


def test_pseudo_translator_only_wraps_the_pseudo_locale(tmp_path):
    inner = GettextTranslator([(write_catalog(tmp_path, "fr", {"Save": "Enregistrer"}), "polyadmin")])
    tr = PseudoTranslator(inner)
    assert tr.gettext(PSEUDO_LOCALE, "Save") == "[Šàvé]"
    assert tr.gettext("fr", "Save") == "Enregistrer"
    assert tr.ngettext(PSEUDO_LOCALE, "%(num)d user", "%(num)d users", 2) % {"num": 2} == "[2 üšérš]"
    assert tr.gettext(PSEUDO_LOCALE, "") == ""


def test_pseudo_translator_leaves_an_already_pseudo_string_alone():
    # R5: the adapter re-translates a host string returned from code (an
    # action's message becoming a flash, a rendered validation error).
    # Re-wrapping it here would double-bracket it, e.g. "[[Délété...]]".
    tr = PseudoTranslator(GettextTranslator())
    already = pseudo("Deleted 1 record.")
    assert tr.gettext(PSEUDO_LOCALE, already) == already
    assert tr.ngettext(PSEUDO_LOCALE, already, pseudo("Deleted %(num)d records."), 1) == already


def test_parse_accept_language_orders_by_q():
    assert parse_accept_language("ru;q=0.2, fr;q=0.8, de") == ["de", "fr", "ru"]
    assert parse_accept_language("fr;q=0, *") == []
    assert parse_accept_language("") == []


@pytest.mark.parametrize(
    ("candidate", "want"),
    [("fr", "fr"), ("FR", "fr"), ("fr-CA", "fr"), ("fr_CA", "fr"), (" ru ", "ru"), ("en-US", "en"),
     ("de", None), ("", None), (None, None), ("en-XA", PSEUDO_LOCALE)],
)
def test_match_locale(candidate, want):
    assert match_locale(["en", "fr", "ru", PSEUDO_LOCALE], candidate) == want


@pytest.mark.parametrize(
    ("header", "want"),
    [("fr-CA,fr;q=0.9,en;q=0.8", "fr"), ("de,ru;q=0.5", "ru"), ("de", None), ("en-US,en;q=0.9", "en"),
     ("*", None), ("ru;q=0.2,fr;q=0.8", "fr"), ("fr;q=0", None), (";;garbage", None)],
)
def test_match_accept_language(header, want):
    assert match_accept_language(["en", "fr", "ru", PSEUDO_LOCALE], header) == want


def test_pseudo_locale_is_never_matched_from_a_base_language():
    assert match_accept_language(["en", PSEUDO_LOCALE], "en-XB") == "en"


def test_resolve_precedence():
    i = I18n(translator=GettextTranslator(), default="en", supported=["en", "fr", "ru"], names={})
    calls = []

    def resolver():
        calls.append(1)
        return "ru"

    assert i.resolve("fr", resolver, "en") == "fr" and calls == []
    assert i.resolve(None, resolver, "fr") == "ru"
    assert i.resolve("xx", lambda: "", "fr") == "fr"
    assert i.resolve(None, None, "de") == "en"


def test_from_admin_defaults():
    i = I18n.from_admin(Admin())
    assert i.default == "en"
    assert i.supported[0] == "en"


def test_from_admin_restricts_and_adds_pseudo():
    i = I18n.from_admin(Admin(locales=["en"], pseudo_locale=True))
    assert i.supported == ["en", PSEUDO_LOCALE]
    assert i.translator.gettext(PSEUDO_LOCALE, "Save") == "[Šàvé]"


def test_from_admin_rejects_bad_config():
    with pytest.raises(ValueError, match="no catalog"):
        I18n.from_admin(Admin(locales=["en", "de"]))
    with pytest.raises(ValueError, match="default locale"):
        I18n.from_admin(Admin(locales=["en"], default_locale="fr", translator=GettextTranslator()))


def test_locale_names(tmp_path):
    write_catalog(tmp_path, "de", {"Save": "Speichern"})
    i = I18n.from_admin(Admin(catalogs=[(tmp_path, "polyadmin")], locale_names={"de": "Deutsch"}, locales=["en", "de"]))
    assert i.options() == [LocaleOption("en", "English"), LocaleOption("de", "Deutsch")]
    assert i.name("pt") == "pt"


def test_context_helpers(tmp_path):
    assert get_locale() == DEFAULT_LOCALE
    assert gettext("Save") == "Save"
    assert ngettext("user", "users", 2) == "users"
    tr = GettextTranslator([(write_catalog(tmp_path, "fr", {"Save": "Enregistrer"}), "polyadmin")])
    with use_locale("fr", tr):
        assert get_locale() == "fr"
        assert gettext("Save") == "Enregistrer"
    assert get_locale() == DEFAULT_LOCALE
    assert N_("Save") == "Save"


def test_stdlib_gettext_is_untouched():
    # The package's `gettext` helper must not shadow the stdlib module.
    assert stdlib_gettext.NullTranslations().gettext("x") == "x"
