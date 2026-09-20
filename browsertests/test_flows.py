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
    # The row opens from its primary key's own cell; there is no trailing
    # View column any more.
    row_link = admin_page.locator("#inline-users table tbody tr td").first.locator("a").first
    expect(row_link).to_be_visible()
    expect(admin_page.locator("#inline-users a", has_text="View")).to_have_count(0)


def test_inline_relation_controls_are_not_clipped(admin_page):
    """The row's relation controls are the admin's own select and
    multi-select, and their popovers are portalled out of the row -- a
    row clips anything taller than itself."""
    admin_page.goto(f"{ADMIN_URL}/organizations/1/edit")
    triggers = admin_page.locator("#inline-users button[aria-haspopup=listbox]")
    expect(triggers.first).to_be_visible()

    triggers.first.click()
    panel = admin_page.locator("body > [class*=bg-popover]").first
    expect(panel).to_be_visible()
    clipped = admin_page.evaluate(
        """() => {
            const panel = document.querySelector('body > [class*=bg-popover]');
            let el = panel.parentElement;
            while (el && el !== document.documentElement) {
                const cs = getComputedStyle(el);
                if (cs.overflowY !== 'visible' || cs.overflowX !== 'visible') return true;
                el = el.parentElement;
            }
            return false;
        }"""
    )
    assert not clipped, "the row's popover is inside a clipping ancestor"


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


def test_a_long_dashboard_widget_scrolls_inside_its_own_card(admin_page):
    """The example's "Recent users" table lists every seeded user. Its
    card has to scroll rather than grow: in a grid, one tall card
    stretches every card beside it to match."""
    admin_page.goto(ADMIN_URL)
    card_body = admin_page.locator("div.ui-scroll-area:has(table)").first
    expect(card_body).to_be_visible()

    overflow = card_body.evaluate("el => el.scrollHeight - el.clientHeight")
    assert overflow > 0, "the widget fits its card; the assertions below would be vacuous"

    header_before = admin_page.locator("div.ui-scroll-area:has(table) thead").first.bounding_box()["y"]
    card_body.evaluate("el => { el.scrollTop = el.scrollHeight }")
    assert card_body.evaluate("el => el.scrollTop") > 0, "the card's body does not scroll"
    header_after = admin_page.locator("div.ui-scroll-area:has(table) thead").first.bounding_box()["y"]
    assert abs(header_after - header_before) <= 1, "the columns scrolled away with the rows"

    # And no card was stretched to the table's full height.
    heights = admin_page.eval_on_selector_all(
        "div.ui-scroll-area", "els => els.map(el => el.getBoundingClientRect().height)"
    )
    assert max(heights) <= 320, f"a widget body grew to {max(heights)}px"


def test_a_flash_message_becomes_a_toast(admin_page):
    """Saving leaves a flash message behind; the toaster raises it."""
    admin_page.goto(f"{ADMIN_URL}/users/create")
    admin_page.fill("#field-email", unique_email())
    admin_page.click("button[type=submit][form=resource-form]")

    expect(admin_page.locator("body > ol[aria-label] > li")).to_have_count(1)


def test_a_toast_is_sonner_shaped_and_waits_while_hovered(admin_page):
    """Sonner's own geometry and its hover-to-hold timer. The toast is
    raised by hand rather than by a save, so these assertions are not
    racing a four-second timer that started with the page load."""
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.evaluate("() => window.toast('Saved', { type: 'success', description: 'Two rows changed.' })")

    toast = admin_page.locator("body > ol[aria-label] > li").first
    expect(toast).to_be_visible()
    box = toast.bounding_box()
    viewport = admin_page.viewport_size
    assert round(box["width"]) == 356, f"Sonner's toast is 356px wide; this one is {box['width']}px"
    assert viewport["width"] - (box["x"] + box["width"]) <= 40, "the toast is not in the right-hand corner"
    assert viewport["height"] - (box["y"] + box["height"]) <= 40, "the toast is not in the bottom corner"

    # The four-second timer holds while the pointer rests on it.
    toast.hover()
    admin_page.wait_for_timeout(4500)
    expect(toast).to_be_visible()

    # Sonner parks the close button on the top-left corner, not inside
    # the toast's right edge.
    close = toast.locator("button")
    assert close.bounding_box()["x"] < box["x"] + 20
    close.click()
    expect(admin_page.locator("body > ol[aria-label] > li")).to_have_count(0)


def test_no_dashboard_widget_scrolls_sideways(admin_page):
    """A card is a fixed column of the grid, so its content wraps rather
    than handing the reader a sideways scrollbar inside the card."""
    admin_page.goto(ADMIN_URL)
    overflows = admin_page.eval_on_selector_all(
        "div.ui-scroll-area",
        "els => els.map(el => el.scrollWidth - el.clientWidth)",
    )
    assert overflows, "no widget bodies on the dashboard; this test would be vacuous"
    assert max(overflows) <= 0, f"a widget body overflows sideways by {max(overflows)}px"


def test_the_user_menu_holds_actions_only(admin_page):
    """The trigger sits directly beside the menu and already shows who
    you are; the menu is for what you can do."""
    admin_page.goto(f"{ADMIN_URL}/users")
    trigger = admin_page.locator('aside button[aria-haspopup="menu"]').last
    expect(trigger).to_be_visible()
    trigger.click()

    menu = admin_page.locator('aside [role="menu"]')
    expect(menu).to_be_visible()
    assert menu.inner_text().strip() == "Sign out", (
        f"the user menu shows {menu.inner_text().strip()!r}, not just its actions"
    )


def test_filtering_by_a_related_record(admin_page):
    """The organization filter is the lookup-backed combobox, because the
    field is in autocomplete_fields. Selecting an option writes the pk
    into the form's hidden input; Apply submits it."""
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.click("button:has-text('Filters')")
    panel = admin_page.locator('[role="dialog"][aria-label="Filters"]')
    expect(panel).to_be_visible()

    trigger = panel.locator('input[role="combobox"]').first
    expect(trigger).to_be_visible()
    trigger.click()
    # Typed, not filled: the lookup fires on keyup (hx-trigger), and
    # fill() sets the value without dispatching one.
    trigger.press_sequentially("Acme", delay=30)
    option = admin_page.locator('[role="listbox"] [data-pk]').first
    expect(option).to_be_visible()
    option.click()
    panel.locator('button[type="submit"]').first.click()

    expect(admin_page).to_have_url(re.compile(r"filter"))
    expect(admin_page.locator("table tbody tr").first).to_be_visible()


def test_the_filter_panel_combobox_is_not_clipped(admin_page):
    """The panel is a scrolling sheet with a focus trap; a popover inside
    it has been clipped by an ancestor's overflow twice before."""
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.click("button:has-text('Filters')")
    panel = admin_page.locator('[role="dialog"][aria-label="Filters"]')
    panel.locator('input[role="combobox"]').first.click()

    clipped = admin_page.evaluate(
        """() => {
            const popover = document.querySelector('body > [class*=bg-popover]');
            if (!popover) return 'no popover';
            let el = popover.parentElement;
            while (el && el !== document.documentElement) {
                const cs = getComputedStyle(el);
                if (cs.overflowY !== 'visible' || cs.overflowX !== 'visible') return true;
                el = el.parentElement;
            }
            return false;
        }"""
    )
    assert clipped is False, f"the panel's combobox popover is clipped ({clipped})"


def test_filtering_by_a_custom_date_range(admin_page):
    """The range is two date inputs and a submit, not a link, so this is
    the one filter whose form has to carry the rest of the list."""
    admin_page.goto(f"{ADMIN_URL}/organizations?search=Acme")
    admin_page.click("button:has-text('Filters')")
    panel = admin_page.locator('[role="dialog"][aria-label="Filters"]')

    # Wide enough to include Acme, founded 2019 in the seed.
    panel.locator('input[name="_range_from"]').fill("2010-01-01")
    panel.locator('input[name="_range_to"]').fill("2030-01-01")
    panel.locator('button[type="submit"]').first.click()

    # The search the reader had must survive applying a range.
    expect(admin_page).to_have_url(re.compile(r"search=Acme"))
    expect(admin_page.locator("table tbody tr").first).to_be_visible()


def test_a_host_written_filter_appears_in_the_panel(admin_page):
    """The example's own Plan filter: the hook, exercised rather than
    only documented."""
    admin_page.goto(f"{ADMIN_URL}/users")
    admin_page.click("button:has-text('Filters')")
    panel = admin_page.locator('[role="dialog"][aria-label="Filters"]')
    expect(panel.locator("text=Paid").first).to_be_visible()
