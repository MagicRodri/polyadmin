"""The shipped catalogs cover every msgid, and the committed .mo files are
the compiled form of the committed .po files."""

import re
from io import BytesIO
from pathlib import Path

import pytest
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent.parent
LOCALE_DIR = ROOT / "polyadmin" / "locale"
LOCALES = ["fr", "ru"]

PLACEHOLDER = re.compile(r"%\((\w+)\)s")


def used_msgids():
    method_map = [("polyadmin/**.py", "python"), ("polyadmin/templates/**.html", "jinja2")]
    options_map = {"polyadmin/templates/**.html": {"extensions": "jinja2.ext.i18n"}}
    keywords = {**DEFAULT_KEYWORDS, "N_": None}
    out = {}
    for _filename, _lineno, message, _comments, _context in extract_from_dir(ROOT, method_map, options_map, keywords=keywords):
        key = message[0] if isinstance(message, tuple) else message
        out[key] = message
    return out


def catalog(locale):
    with open(LOCALE_DIR / locale / "LC_MESSAGES" / "polyadmin.po", "rb") as f:
        return read_po(f, locale=locale)


def test_extraction_finds_the_framework_strings():
    assert len(used_msgids()) >= 50


@pytest.mark.parametrize("locale", LOCALES)
def test_catalog_is_complete(locale):
    used = used_msgids()
    cat = catalog(locale)
    missing, empty = [], []
    for key in used:
        message = cat.get(key)
        if message is None:
            missing.append(key)
        elif (isinstance(message.string, tuple) and not all(message.string)) or not message.string:
            empty.append(key)
    unused = [m.id if isinstance(m.id, str) else m.id[0] for m in cat if m.id and (m.id if isinstance(m.id, str) else m.id[0]) not in used]
    assert not missing, f"{locale}: run pybabel update; missing {missing}"
    assert not empty, f"{locale}: untranslated {empty}"
    assert not unused, f"{locale}: obsolete entries {unused}"


@pytest.mark.parametrize("locale", LOCALES)
def test_mo_matches_po(locale):
    compiled = BytesIO()
    write_mo(compiled, catalog(locale))
    committed = (LOCALE_DIR / locale / "LC_MESSAGES" / "polyadmin.mo").read_bytes()
    assert compiled.getvalue() == committed, f"{locale}: run pybabel compile"


@pytest.mark.parametrize("locale", LOCALES)
def test_translations_keep_every_placeholder(locale):
    """No msgstr may drop (or invent) a %(name)s placeholder relative to its
    msgid/msgid_plural: a singular form may omit %(num)s only when the
    English singular msgid also lacks it (e.g. "%d row" has no %(num)s in
    its own text, only in the plural)."""
    cat = catalog(locale)
    bad = []
    for message in cat:
        if not message.id:
            continue
        if isinstance(message.id, tuple):
            singular_id, plural_id = message.id
            forms = message.string if isinstance(message.string, tuple) else (message.string,)
            expected_sets = [set(PLACEHOLDER.findall(singular_id))] + [set(PLACEHOLDER.findall(plural_id))] * (len(forms) - 1)
        else:
            forms = (message.string,)
            expected_sets = [set(PLACEHOLDER.findall(message.id))]
        for index, (form, expected) in enumerate(zip(forms, expected_sets)):
            found = set(PLACEHOLDER.findall(form or ""))
            if found != expected:
                bad.append((message.id, index, sorted(expected), sorted(found)))
    assert not bad, f"{locale}: placeholder mismatch (msgid, msgstr index, expected, found): {bad}"
