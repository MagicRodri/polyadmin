"""Browser coverage for the flows a unit test cannot see.

Every assertion checks state the server actually holds, or a style the
browser actually resolved. Two past failures are the reason: scripts
that asserted the absence of an error string and passed against a form
that had never been submitted, and a login page that shipped with a
panel the same colour as the page behind it.
"""

import re
import uuid

from conftest import ADMIN_URL
from playwright.sync_api import expect


def unique_email():
    return f"bt-{uuid.uuid4().hex[:10]}@example.com"


def create_user(page, email):
    page.goto(f"{ADMIN_URL}/users/create")
    page.fill("#field-email", email)
    page.click("button[type=submit][form=resource-form]")
    expect(page).not_to_have_url(re.compile(r"/users/create$"))
    return page.url


def rows_matching(page, email):
    page.goto(f"{ADMIN_URL}/users?search={email}")
    return page.locator("table tbody tr")


def test_unauthenticated_visit_is_sent_to_login(anon_page):
    anon_page.goto(f"{ADMIN_URL}/users")
    # A regex, not a glob: "?" is a wildcard in Playwright's URL globs.
    expect(anon_page).to_have_url(re.compile(r"/login\?next=%2Fadmin%2Fusers$"))


def test_wrong_password_is_refused_and_keeps_the_email(anon_page):
    anon_page.goto(f"{ADMIN_URL}/login")
    anon_page.fill("#login-identifier", "admin@example.com")
    anon_page.fill("#login-password", "not the password")
    anon_page.click("form:has(#login-identifier) button[type=submit]")

    expect(anon_page.get_by_role("alert")).to_contain_text("match an account")
    expect(anon_page.locator("#login-identifier")).to_have_value("admin@example.com")


def test_signing_in_lands_on_the_requested_page(anon_page):
    anon_page.goto(f"{ADMIN_URL}/users")
    anon_page.fill("#login-identifier", "admin@example.com")
    anon_page.fill("#login-password", "polyadmin")
    anon_page.click("form:has(#login-identifier) button[type=submit]")

    expect(anon_page).to_have_url(f"{ADMIN_URL}/users")
    expect(anon_page.locator("table tbody tr").first).to_be_visible()


def test_login_panel_is_visible_against_the_page(anon_page):
    """The regression this suite exists for.

    The panel and the page background were both bg-muted, so the card
    read as half-width with text floating beside it. Only comparing the
    two resolved colours catches that.
    """
    anon_page.goto(f"{ADMIN_URL}/login")
    for dark in (False, True):
        anon_page.evaluate("dark => document.documentElement.classList.toggle('dark', dark)", dark)
        panel = anon_page.evaluate(
            """() => {
                const aside = document.querySelector('form:has(#login-identifier)').parentElement.lastElementChild;
                const style = getComputedStyle(aside);
                return {background: style.backgroundColor, image: style.backgroundImage};
            }"""
        )
        page_background = anon_page.evaluate(
            "() => getComputedStyle(document.querySelector('form:has(#login-identifier)').closest('body > div')).backgroundColor"
        )
        assert panel["image"] != "none" or panel["background"] != page_background, (
            f"panel is invisible against the page in {'dark' if dark else 'light'} mode: {panel}"
        )


def test_login_card_is_two_columns_at_desktop_width(anon_page):
    anon_page.goto(f"{ADMIN_URL}/login")
    form = anon_page.locator("form:has(#login-identifier)").bounding_box()
    aside = anon_page.locator("form:has(#login-identifier) + div").bounding_box()
    assert aside["x"] >= form["x"] + form["width"] - 2, "the panel is not beside the form"


def test_create_a_record(admin_page):
    email = unique_email()
    create_user(admin_page, email)
    expect(rows_matching(admin_page, email)).to_have_count(1)


def test_save_and_add_another_returns_to_an_empty_form(admin_page):
    email = unique_email()
    admin_page.goto(f"{ADMIN_URL}/users/create")
    admin_page.fill("#field-email", email)
    admin_page.click('button[name="_addanother"]')

    expect(admin_page).to_have_url(f"{ADMIN_URL}/users/create")
    expect(admin_page.locator("#field-email")).to_have_value("")
    expect(rows_matching(admin_page, email)).to_have_count(1)


def test_edit_a_record(admin_page):
    email = unique_email()
    changed = unique_email()
    record_url = create_user(admin_page, email)

    admin_page.goto(f"{record_url}/edit")
    admin_page.fill("#field-email", changed)
    admin_page.click("button[type=submit][form=resource-form]")

    # Let the save's own navigation commit: going straight to the list
    # races it, and Chromium aborts the second navigation.
    expect(admin_page).not_to_have_url(re.compile(r"/edit$"))
    expect(rows_matching(admin_page, changed)).to_have_count(1)
    expect(rows_matching(admin_page, email)).to_have_count(0)


def test_delete_selected_removes_only_the_ticked_rows(admin_page):
    keep, drop = unique_email(), unique_email()
    create_user(admin_page, keep)
    create_user(admin_page, drop)

    rows = rows_matching(admin_page, drop)
    expect(rows).to_have_count(1)
    rows.locator('input[type="checkbox"]').check()
    admin_page.locator("#bulk-actions-form button").click()
    admin_page.get_by_role("option", name="Delete selected").click()
    admin_page.get_by_role("button", name="Confirm").click()

    expect(rows_matching(admin_page, drop)).to_have_count(0)
    expect(rows_matching(admin_page, keep)).to_have_count(1)


def test_search_filters_the_table_without_a_reload(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users")
    before = admin_page.locator("table tbody tr").count()
    assert before > 1, "need more than one row to prove filtering"

    # #search, not input[name=search]: the bulk-actions form carries a
    # hidden mirror of the same name.
    #
    # Typed, not filled: the search bar submits on keyup, and fill() sets
    # the value without producing key events.
    admin_page.locator("#search").press_sequentially("admin@example.com")
    expect(admin_page.locator("table tbody tr")).to_have_count(1)
    # The swapped region and its toolbar both have to survive the swap.
    expect(admin_page.locator("#resource-list")).to_be_visible()
    expect(admin_page.locator("#search")).to_be_visible()


def test_missing_record_renders_a_styled_page(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users/99999999")
    expect(admin_page.get_by_text("404")).to_be_visible()
    expect(admin_page.get_by_role("link", name="Back to the admin")).to_be_visible()
    background = admin_page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert background not in ("rgba(0, 0, 0, 0)", ""), "the error page is unthemed"


def test_a_non_superuser_may_read_but_not_write(viewer_page):
    viewer_page.goto(f"{ADMIN_URL}/users")
    expect(viewer_page.locator("table tbody tr").first).to_be_visible()
    expect(viewer_page.locator('a[href$="/users/create"]')).to_have_count(0)

    viewer_page.goto(f"{ADMIN_URL}/tools/broadcast")
    expect(viewer_page.get_by_text("403")).to_be_visible()


def test_select_is_arrow_navigable(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users/create")
    trigger = admin_page.locator("[x-data*='adminSelect'] button").first
    trigger.click()
    expect(trigger).to_have_attribute("aria-expanded", "true")

    trigger.press("ArrowDown")
    # aria-activedescendant lives on the combobox, not on the listbox it
    # controls, which is what the ARIA pattern specifies.
    assert trigger.get_attribute("aria-activedescendant")


def test_inline_table_shows_its_row_actions(admin_page):
    admin_page.goto(f"{ADMIN_URL}/organizations/1")
    expect(admin_page.locator("#inline-users")).to_be_visible()

    overflow = admin_page.evaluate(
        """() => {
            const table = document.querySelector('#inline-users table');
            const scroller = table.parentElement;
            return table.scrollWidth - scroller.clientWidth;
        }"""
    )
    assert overflow <= 0, f"the inline table overflows its card by {overflow}px"
    row_link = admin_page.locator("#inline-users table tbody tr td:last-child a", has_text="View").first
    expect(row_link).to_be_visible()


def test_inline_selects_are_not_clipped(admin_page):
    admin_page.goto(f"{ADMIN_URL}/organizations/1/edit")
    clipped = admin_page.evaluate(
        """() => [...document.querySelectorAll('#inline-users select:not([multiple])')]
            .filter(select => select.scrollWidth > Math.ceil(select.getBoundingClientRect().width))
            .length"""
    )
    assert clipped == 0, "a select is narrower than its widest option"


def test_no_admin_page_scrolls_sideways(admin_page):
    for path in ("", "/users", "/users/create", "/organizations/1", "/organizations/1/edit"):
        admin_page.goto(f"{ADMIN_URL}{path}")
        overflow = admin_page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0, f"{path or '/'} scrolls sideways by {overflow}px"


def test_sidebar_rail_sits_on_the_sidebar_edge(admin_page):
    admin_page.goto(f"{ADMIN_URL}/users")
    sidebar = admin_page.locator("aside").bounding_box()
    rail = admin_page.locator('aside button[aria-label="Toggle sidebar"].cursor-w-resize').bounding_box()
    rail_centre = rail["x"] + rail["width"] / 2
    sidebar_edge = sidebar["x"] + sidebar["width"]
    assert abs(rail_centre - sidebar_edge) <= 2, (
        f"the rail is centred at {rail_centre}px, the sidebar ends at {sidebar_edge}px"
    )
