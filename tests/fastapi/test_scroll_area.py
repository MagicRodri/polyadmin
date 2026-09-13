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
    assert ui("table", "scroll") in section


def test_list_table_uses_the_registrys_scroll_part():
    client, _, _ = make_client()
    assert ui("table", "scroll") in client.get("/admin/users").text


def test_many_to_many_listbox_in_an_edit_row_is_capped():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")
    # More options than the cap, or there is nothing to cap.
    for i in range(1, INLINE_MULTISELECT_ROWS + 5):
        org_admin._store[100 + i] = Organization(100 + i, f"Team {i}")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert "<select multiple" in section, "no multi-select in the edit row"
    assert f'size="{INLINE_MULTISELECT_ROWS}"' in section
    # It must not be sized to the option count.
    assert f'size="{INLINE_MULTISELECT_ROWS + 5}"' not in section


def test_many_to_many_listbox_in_an_edit_row_uses_the_scroll_area_styling():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")
    org_admin._store[101] = Organization(101, "Team")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert ui("scroll-area", "y") in section


def test_inline_edit_controls_are_actually_styled():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    section = _inline_section(client.get(f"/admin/organizations/{org.id}/edit").text)
    assert "<input" in section, "no controls in the edit row"
    # The resolved classes, not the expression that produces them (that
    # the expression never leaks is the suite-wide guard in conftest).
    assert ui("input", "size-sm") in section
    # No plain <select> to check here: the inline's own fk_field is
    # implied by context and never rendered, so the only select in this
    # fixture's row is the many-to-many, which uses the table-cell part.
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
