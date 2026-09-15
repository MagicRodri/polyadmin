"""Localisation, checked in a real browser: what the unit suites cannot
see is Intl formatting and the switcher round-trip."""

import re

from conftest import ADMIN_URL
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
ALLOWED = re.compile(
    r"@example\.com"
    r"|Acme Corp|Widgets Inc|Globex Corporation|Initech"
    r"|^(?:Free|Pro|Enterprise)$"
    r"|Administrator|Billing|Support|Auditor|Content Editor|Release Manager|Read Only|Security Officer"
    r"|Demo Admin|Demo Viewer|Amélie"
    r"|^(?:Active|Inactive)$|Account created|user #\d+"
    r"|English|Français|Русский|Pseudo \(en-XA\)"
    r"|^[A-Z]{1,2}$"
    r"|^\W*\d[\d\s.,:/-]*\W*$"
    # Intl.DateTimeFormat("en-XA", ...): the pseudo locale has no CLDR
    # data of its own, so the browser falls back to plain English
    # month/day formatting ("Mar 1, 2019") -- a date value, not chrome.
    r"|^[A-Z][a-z]{2} \d{1,2}, \d{4}$"
)


def visible_untranslated(page):
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
                if (/\p{L}/u.test(text)) out.push(node.textContent.trim());
            }
            return out;
        }"""
    )


def test_no_visible_english_in_the_pseudo_locale(admin_page):
    admin_page.context.add_cookies([{"name": "admin_locale", "value": "en-XA", "url": ADMIN_URL}])
    for path in ("", "/users", "/users/create", "/organizations/1", "/organizations/1/edit"):
        admin_page.goto(f"{ADMIN_URL}{path}")
        left = [t for t in visible_untranslated(admin_page) if not ALLOWED.search(t)]
        assert not left, f"{path or '/'}: {left}"


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
    context.close()


def test_switcher_round_trip(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.locator('header button[aria-haspopup="menu"]').click()
    admin_page.get_by_role("menuitemradio", name="Français").click()
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    admin_page.goto(f"{ADMIN_URL}/organizations")
    expect(admin_page.locator("html")).to_have_attribute("lang", "fr")
    admin_page.context.clear_cookies()


def test_resolver_serves_the_principals_language(amelie_page):
    amelie_page.goto(f"{ADMIN_URL}/users")
    expect(amelie_page.locator("html")).to_have_attribute("lang", "fr")
