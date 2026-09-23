"""Bounded relation cells in a tabular inline."""

from polyadmin.core.inline import INLINE_MULTISELECT_ROWS
from polyadmin.ui import ui
from tests.fastapi.test_inlines import Organization, make_client, seed_org_with_users


def _inline_section(page):
    """Just the inline region, bounded at the page's own action bar --
    the parent's controls render further down the same page and would
    otherwise be counted as part of the section."""
    section = page.split('id="inline-users"')[1]
    return section.split(ui("page", "actions"))[0]


def test_a_readonly_stacked_inline_record_scrolls_inside_its_own_card():
    """A related record with many fields otherwise grows its card to fit
    them, same problem as a long dashboard widget -- see
    TestAStackedInlineRecordScrollsInsideItsOwnCard on the Go side."""
    client, org_admin, user_admin = make_client(inline_layout="stacked")
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}").text)
    assert "a@example.com" in section, "the related record rendered nothing"
    panel_body = ui("panel", "body")
    assert panel_body in section, "the related record's card is not the bounded scroll box"
    assert "max-h-" in panel_body and "overflow-y-auto" in panel_body
    assert "ui-scroll-area" in panel_body


def test_an_editable_stacked_inline_record_scrolls_inside_its_own_card():
    client, org_admin, user_admin = make_client(inline_layout="stacked")
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert "<form" in section, "the edit row rendered nothing; the assertion below would be vacuous"
    assert ui("panel", "body") in section, "the editable row's card is not the bounded scroll box"


def test_many_to_many_cell_in_a_tabular_inline_is_bounded():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")
    # The cell has to actually hold several relations, or the assertion
    # below would pass against an empty one and prove nothing.
    users[0].teams = [Organization(9, "Platform"), Organization(10, "Security")]

    section = _inline_section(client.get(f"/admin/organizations/{org.id}").text)
    assert "Platform" in section, "the many-to-many cell rendered nothing"
    assert ui("scroll-area", "x") in section


def test_only_many_to_many_cells_are_bounded():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")
    users[0].teams = [Organization(9, "Platform")]

    section = _inline_section(client.get(f"/admin/organizations/{org.id}").text)
    assert section.count(ui("scroll-area", "x")) == 1


def test_tabular_inline_table_can_scroll_rather_than_clip():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}").text)
    assert ui("table", "inline-scroll") in section


def test_a_long_tabular_inline_scrolls_inside_its_own_card():
    """Unlike the top-level list table (meant to grow the page), a
    tabular inline sits inside a parent's detail/edit page -- many child
    rows should scroll in place, not stretch the page, same reasoning as
    the widget and stacked-inline cards."""
    client, org_admin, user_admin = make_client()
    emails = [f"user{i}@example.com" for i in range(50)]
    org, _ = seed_org_with_users(org_admin, user_admin, *emails)

    section = _inline_section(client.get(f"/admin/organizations/{org.id}").text)
    assert "user49@example.com" in section, "not every row rendered; the assertion below would be vacuous"
    inline_scroll = ui("table", "inline-scroll")
    assert "max-h-" in inline_scroll and "overflow-y-auto" in inline_scroll
    assert "ui-scroll-area" in inline_scroll
    # The main list table must keep the page-level scroll it already had.
    assert "max-h-" not in ui("table", "scroll")


def test_scroll_area_contains_overscroll_rather_than_chaining_to_the_page():
    """Without overscroll-behavior, wheel input that outruns a bounded
    box's own scroll range chains into whichever ancestor scrolls next --
    on the edit page that is the whole document, so scrolling to the
    bottom of a tabular inline suddenly yanks the page too. Verified live
    with Playwright: scrollY stayed 0 with `overscroll-behavior: contain`
    set, and jumped to 1200 without it."""
    client, _, _ = make_client()
    page = client.get("/admin/users").text
    idx = page.find(".ui-scroll-area {")
    assert idx >= 0, "no .ui-scroll-area rule on the page; the assertion below would be vacuous"
    rule = page[idx : idx + 500]
    assert "overscroll-behavior: contain" in rule, (
        f"the scroll area does not contain overscroll, so scrolling past its own edge leaks into the page: {rule!r}"
    )


def test_list_table_uses_the_registrys_scroll_part():
    client, _, _ = make_client()
    assert ui("table", "scroll") in client.get("/admin/users").text


def test_many_to_many_in_an_edit_row_is_the_shadcn_control():
    """The row holds the same trigger-and-popover control the full form
    uses, not a native <select multiple> sized to its options."""
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")
    for i in range(1, INLINE_MULTISELECT_ROWS + 5):
        org_admin._store[100 + i] = Organization(100 + i, f"Team {i}")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert "<select multiple" not in section, "the native listbox is still there"
    assert 'aria-haspopup="listbox"' in section, "no shadcn multi-select in the edit row"
    # Its popover leaves the row rather than being clipped by it.
    assert 'x-teleport="body"' in section
    # Nothing is sized to the option count any more.
    assert f'size="{INLINE_MULTISELECT_ROWS}"' not in section


def test_a_relation_cell_in_an_edit_row_is_the_shadcn_select():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    # One hidden input carrying the value, as ui/select posts it.
    assert "adminMultiSelect()" in section or "adminSelect()" in section


def test_inline_edit_controls_are_actually_styled():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert "<input" in section, "no controls in the edit row"
    # The resolved classes, not the expression that produces them (that
    # the expression never leaks is the suite-wide guard in conftest).
    assert ui("input", "size-sm") in section
    # No plain <select> to check here: the inline's own fk_field is
    # implied by context and never rendered, so the only relation control
    # in this fixture's row is the many-to-many, whose compact trigger
    # uses the table-cell part.
    assert ui("select", "cell-multi") in section


def test_page_with_a_tabular_inline_uses_the_wide_body():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    for path in ("", "/edit"):
        page = client.get(f"/admin/organizations/{org.id}{path}").text
        assert ui("page", "body-wide") in page, path
        # The action bar has to widen with it or the buttons drift out of
        # line with the card above them.
        assert ui("page", "actions-inner-wide") in page, path


def test_a_plain_form_keeps_the_narrow_body():
    client, _, user_admin = make_client()
    user = user_admin.create({"email": "a@example.com", "is_active": True})

    page = client.get(f"/admin/users/{user.id}/edit").text
    assert "resource-form" in page, "not a form page"
    assert ui("page", "body") in page
    assert ui("page", "body-wide") not in page


def test_a_stacked_inline_keeps_the_narrow_body():
    client, org_admin, user_admin = make_client(inline_layout="stacked")
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")
    page = client.get(f"/admin/organizations/{org.id}").text
    assert ui("page", "body-wide") not in page


def test_select_in_a_table_cell_sizes_to_its_content():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert ui("select", "cell-multi") in section
    # The w-full base would defeat the whole point.
    assert ui("select", "size-sm") not in section
