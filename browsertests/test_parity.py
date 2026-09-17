"""The small parity batch in a real browser, on the example app's seed data
(docs/lists.md).

Every test that writes creates what it writes first, so the other files'
tests still find the seed intact.
"""

import re
import uuid

from conftest import ADMIN_URL
from playwright.sync_api import expect

NAME_FIELD = "#field-name"


def create_organization(page, name):
    page.goto(f"{ADMIN_URL}/organizations/create")
    page.fill(NAME_FIELD, name)
    page.click("button[type=submit][form=resource-form]")
    expect(page).not_to_have_url(re.compile(r"/organizations/create$"))


def test_editing_from_a_filtered_list_returns_to_it(admin_page):
    """preserve_filters: the trail out of a filtered list leads back into it."""
    name = f"Filtered {uuid.uuid4().hex[:8]}"
    create_organization(admin_page, name)

    admin_page.goto(f"{ADMIN_URL}/organizations?search={name}")
    expect(admin_page.locator("table tbody tr")).to_have_count(1)
    admin_page.locator("table tbody tr").first.get_by_role("button", name="Open menu").click()
    admin_page.get_by_role("menuitem", name="Edit").click()

    admin_page.fill(NAME_FIELD, f"{name} renamed")
    admin_page.click("button[type=submit][form=resource-form]")

    # The record's own page, whose breadcrumb leads back to the list as it
    # was left -- not to the bare list. Scoped to the breadcrumb: the
    # sidebar has its own "Organization" link, to the bare list.
    admin_page.locator("nav[aria-label='Breadcrumb']").get_by_role("link", name="Organization").click()
    expect(admin_page).to_have_url(re.compile(r"search=Filtered"))
    expect(admin_page.locator("table tbody tr")).to_have_count(1)


def test_save_as_new_clones_a_record(admin_page):
    """save_as: the submitted values become a new record, the original stands."""
    name = f"Clonable {uuid.uuid4().hex[:8]}"
    create_organization(admin_page, name)

    admin_page.goto(f"{ADMIN_URL}/organizations?search={name}")
    admin_page.locator("table tbody tr").first.get_by_role("button", name="Open menu").click()
    admin_page.get_by_role("menuitem", name="Edit").click()

    admin_page.fill(NAME_FIELD, f"{name} copy")
    admin_page.get_by_role("button", name="Save as new").click()
    # The copy's own page, which is where a create lands. Waited for before
    # navigating away, or the goto below aborts the save in flight.
    expect(admin_page).to_have_url(re.compile(r"/organizations/\d+(?:\?|$)"))

    # Both exist: the original under its own name, the copy under the new one.
    admin_page.goto(f"{ADMIN_URL}/organizations?search={name}")
    expect(admin_page.locator("table tbody tr")).to_have_count(2)


def test_the_date_filter_narrows_the_list(admin_page):
    """date filter: declared like any other, it lives in the filter panel."""
    admin_page.goto(f"{ADMIN_URL}/organizations")
    admin_page.get_by_role("button", name="Filters").click()
    panel = admin_page.get_by_role("dialog") if admin_page.get_by_role("dialog").count() else admin_page
    expect(panel.get_by_text("Any date").first).to_be_visible()

    before = admin_page.locator("table tbody tr").count()
    panel.get_by_role("link", name="This year").first.click()
    # Python percent-encodes the filter key in list URLs; the Go suite's
    # copy expects the brackets literal.
    expect(admin_page).to_have_url(re.compile(r"filter%5Bfounded%5D=year"))
    # The seed spreads founded dates over several years, so this year's
    # slice is smaller than the whole list.
    assert admin_page.locator("table tbody tr").count() < before

    # And nothing above the table any more.
    expect(admin_page.locator("nav[aria-label='All dates']")).to_have_count(0)


def test_a_list_cell_links_to_its_record(admin_page):
    """list_display_links: the named column, not the id, opens the record."""
    admin_page.goto(f"{ADMIN_URL}/organizations")
    admin_page.get_by_role("link", name="Acme Corp").first.click()
    expect(admin_page).to_have_url(re.compile(r"/organizations/1"))
    expect(admin_page.get_by_text("Acme Corp").first).to_be_visible()
