"""Localisation, checked in a real browser: what the unit suites cannot
see is Intl formatting and the switcher round-trip."""

import re

from conftest import ADMIN_URL, SUPERUSER, _sign_in
from playwright.sync_api import expect

# Data values in the example app, and the switcher's untranslated names.
# Everything here is either a seeded record value (session.py/models.py)
# or computed straight from one -- avatar/brand initials
# (sidebar.html's `display_name[:2] | upper` and `site_title[:2] | upper`)
# and the dashboard's chart/timeline widgets (main.py builds these from
# literal Python strings and the widget templates render
# label/title/time/description raw, the same way widgets/table.html
# renders row cells raw -- see donut.html and timeline.html). App chrome
# goes through {{ _(...) }} instead, which the pseudo locale brackets,
# and the sweep below strips bracketed text before checking, so none of
# that needs listing here.
#
# Every alternative is anchored to a whole text run: a substring match
# would let untranslated chrome through on the back of a data value
# ("Is Active" contains "Active", "Supported" contains "Support").
# A many-to-many value is its labels joined with ", ".
ROLES = (
    "Administrator|Billing|Support|Auditor|Content Editor|Release Manager|Read Only|Security Officer"
)
ALLOWED = re.compile(
    r"^[\w.+-]+@example\.com$"
    r"|^(?:Acme Corp|Widgets Inc|Globex Corporation|Initech)$"
    # The seed's filler organizations, data like the four named ones.
    r"|^Org \d\d Holdings$"
    r"|^(?:Free|Pro|Enterprise)$"
    rf"|^(?:{ROLES})(?:, (?:{ROLES}))*$"
    r"|^(?:Demo Admin|Demo Viewer|Amélie)$"
    r"|^(?:Active|Inactive|Account created|user #\d+)$"
    r"|^(?:English|Français|Русский|Pseudo \(en-XA\))$"
    r"|^[A-Z]{1,2}$"
    r"|^\W*\d[\d\s.,:/-]*\W*$"
    # Intl.DateTimeFormat("en-XA", ...): the pseudo locale has no CLDR
    # data of its own, so the browser falls back to plain English
    # month/day formatting ("Mar 1, 2019") -- a date value, not chrome.
    r"|^[A-Z][a-z]{2} \d{1,2}, \d{4}$"
)
PSEUDO_COOKIE = {"name": "admin_locale", "value": "en-XA", "url": ADMIN_URL}


def visible_untranslated(page):
    """Each visible text run with letters left once bracketed (pseudo-
    translated) text is removed: the remainder, which is what ALLOWED
    must match, and the full run, for the failure message."""
    return page.evaluate(
        r"""() => {
            const out = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const node = walker.currentNode, el = node.parentElement;
                if (!el || el.closest("script,style,[hidden]") || !el.getClientRects().length) continue;
                let text = node.textContent.trim();
                let prev;
                do { prev = text; text = text.replace(/\[[^\[\]]*\]/g, ""); } while (text !== prev);
                if (/\p{L}/u.test(text)) out.push([text.trim(), node.textContent.trim()]);
            }
            return out;
        }"""
    )


def assert_all_translated(page, path):
    page.goto(f"{ADMIN_URL}{path}")
    left = [full for rest, full in visible_untranslated(page) if not ALLOWED.search(rest)]
    assert not left, f"{path or '/'}: {left}"


def test_allowed_matches_whole_runs_only():
    for data in ("Acme Corp", "Pro", "Support, Billing", "viewer@example.com", "user #3", "Mar 1, 2019"):
        assert ALLOWED.search(data), data
    for chrome in ("Is Active", "Profile", "Supported", "Acme Corporation", "Support,Billing"):
        assert not ALLOWED.search(chrome), chrome


def test_no_visible_english_in_the_pseudo_locale(admin_page):
    admin_page.context.add_cookies([PSEUDO_COOKIE])
    # /organizations/999 is the admin's own 404 page.
    for path in ("", "/users", "/users/create", "/organizations/1", "/organizations/1/edit", "/organizations/999"):
        assert_all_translated(admin_page, path)


def test_no_visible_english_on_the_login_page_in_the_pseudo_locale(anon_page):
    anon_page.context.add_cookies([PSEUDO_COOKIE])
    assert_all_translated(anon_page, "/login")


def test_french_browser_gets_french_pages_and_dates(browser):
    context = browser.new_context(locale="fr-FR", viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto(f"{ADMIN_URL}/login")
    expect(page.locator("html")).to_have_attribute("lang", "fr")
    page.fill("#login-identifier", "admin@example.com")
    page.fill("#login-password", "polyadmin")
    page.click("form:has(#login-identifier) button[type=submit]")
    page.goto(f"{ADMIN_URL}/organizations")
    founded = page.locator('time[data-format="date"]').first
    expect(founded).not_to_have_text(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
    expect(founded).to_have_text(re.compile(r"mars|janv|févr|avr|mai|juin|juil|août|sept|oct|nov|déc"))
    # Chrome from the framework catalog, not just a translated date.
    expect(page.locator("aside a", has_text="Tableau de bord")).to_be_visible()
    expect(page.locator("#search")).to_have_attribute("placeholder", "Rechercher…")
    expect(page.get_by_role("button", name="Exporter")).to_be_visible()
    expect(page.get_by_role("link", name="Nouveau")).to_be_visible()
    context.close()


def test_date_picker_weekdays_are_french_under_fr(browser):
    context = browser.new_context(locale="fr-FR", viewport={"width": 1440, "height": 900})
    page = context.new_page()
    _sign_in(page, SUPERUSER)
    page.goto(f"{ADMIN_URL}/organizations/1/edit")
    page.get_by_role("button", name="Ouvrir le calendrier").click()
    weekdays = page.locator('[x-data="adminCalendar()"] [role="columnheader"]')
    expect(weekdays.first).to_have_text(re.compile(r"^lun\.?$"))
    expect(weekdays.last).to_have_text(re.compile(r"^dim\.?$"))
    context.close()


def test_switcher_round_trip(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.locator('header button[aria-haspopup="menu"]').click()
    admin_page.get_by_role("menuitemradio", name="Français").click()
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    admin_page.goto(f"{ADMIN_URL}/organizations")
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    admin_page.context.clear_cookies()


def test_switcher_choice_survives_signing_out_and_in(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.locator('header button[aria-haspopup="menu"]').click()
    admin_page.get_by_role("menuitemradio", name="Français").click()
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    admin_page.locator('button[x-ref="userTrigger"]').click()
    admin_page.get_by_role("menuitem", name="Se déconnecter").click()
    expect(admin_page).to_have_url(re.compile(r"/login"))
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    _sign_in(admin_page, SUPERUSER)
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")


def _format(page, markup, lang):
    """Run the page's formatter over `markup` under `lang` and return each
    element's text; the page's own lang and content are left as they were."""
    return page.evaluate(
        """([markup, lang]) => {
            const root = document.documentElement, before = root.lang;
            const box = document.createElement("div");
            box.innerHTML = markup;
            document.body.appendChild(box);
            root.lang = lang;
            try {
                window.polyadminFormat(box);
                return Array.from(box.children, (el) => el.textContent);
            } finally {
                root.lang = before;
                box.remove();
            }
        }""",
        [markup, lang],
    )


def test_formatter_keeps_years_below_100(anon_page):
    anon_page.goto(f"{ADMIN_URL}/login")
    date, naive = _format(
        anon_page,
        '<time datetime="0099-03-01" data-format="date">0099-03-01</time>'
        '<time datetime="0099-03-01T10:30" data-format="datetime">0099-03-01T10:30</time>',
        "en",
    )
    assert re.fullmatch(r"Mar 1, 0*99", date), date
    assert "1999" not in naive and naive.startswith("Mar 1, 99"), naive


def test_formatter_survives_bad_values_and_keeps_decimal_precision(anon_page):
    anon_page.goto(f"{ADMIN_URL}/login")
    iso = '<time datetime="2019-03-01" data-format="date">2019-03-01</time>'
    # An unknown lang: nothing formats, and nothing throws.
    assert _format(anon_page, iso, "not a locale!") == ["2019-03-01"]
    # More fraction digits than NumberFormat takes: clamped to 20, and the
    # values after it still format.
    many = '<span data-format="decimal" data-value="0.1234567890123456789012345">x</span>'
    assert _format(anon_page, many + iso, "en") == ["0.12345678901234567890", "Mar 1, 2019"]
    # Past what a double holds, the decimal string keeps every digit.
    big = '<span data-format="decimal" data-value="12345678901234567.89">x</span>'
    assert _format(anon_page, big, "en") == ["12,345,678,901,234,567.89"]


def test_resolver_serves_the_principals_language(amelie_page):
    amelie_page.goto(f"{ADMIN_URL}/users")
    expect(amelie_page.locator("html")).to_have_attribute("lang", "fr")
