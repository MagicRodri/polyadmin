"""The delete preview in a real browser, on the example app's seed data.

The organization and role pages read seeded records without changing
them; every test that deletes something creates what it deletes first,
so the other files' tests still find the seed intact.
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


def test_organization_delete_lists_its_users(admin_page):
    admin_page.goto(f"{ADMIN_URL}/organizations/4/delete")  # Initech
    expect(admin_page.get_by_text("This will also delete")).to_be_visible()
    expect(admin_page.get_by_role("link", name="samir@example.com")).to_be_visible()


def test_deleting_an_organization_removes_it(admin_page):
    name = f"Doomed {uuid.uuid4().hex[:8]}"
    create_organization(admin_page, name)
    admin_page.goto(f"{ADMIN_URL}/organizations?search={name}")
    admin_page.locator("table tbody tr").first.get_by_role("button", name="Open menu").click()
    admin_page.get_by_role("menuitem", name="Delete").click()
    expect(admin_page.get_by_text(f"«{name}»")).to_be_visible()
    admin_page.click("#delete-confirm")
    admin_page.goto(f"{ADMIN_URL}/organizations?search={name}")
    expect(admin_page.locator("table tbody tr")).to_have_count(0)


def test_an_assigned_role_cannot_be_deleted(admin_page):
    admin_page.goto(f"{ADMIN_URL}/roles/2/delete")  # Billing
    expect(admin_page.get_by_text("This can't be deleted")).to_be_visible()
    expect(admin_page.locator("#delete-confirm")).to_have_count(0)


def test_bulk_delete_of_all_matching_goes_through_the_confirmation_page(admin_page):
    tag = uuid.uuid4().hex[:8]
    for i in (1, 2):
        create_organization(admin_page, f"Bulk {tag} {i}")
    # page_size=1: two matches on a one-row page is what offers "select all matching".
    admin_page.goto(f"{ADMIN_URL}/organizations?search=Bulk+{tag}&page_size=1")
    admin_page.locator("thead input[type=checkbox]").check()
    admin_page.get_by_role("button", name=re.compile(r"Select all 2 matching")).click()
    admin_page.locator("button[aria-haspopup=listbox]").click()
    admin_page.get_by_role("option", name="Delete selected").click()
    expect(admin_page.get_by_text("Delete 2 records?")).to_be_visible()
    admin_page.click("#delete-confirm")
    admin_page.goto(f"{ADMIN_URL}/organizations?search=Bulk+{tag}")
    expect(admin_page.locator("table tbody tr")).to_have_count(0)
