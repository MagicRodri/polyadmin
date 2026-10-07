"""The SQL-backed Projects resources, in a real browser.

Nothing here changes the seed: the create and the delete are both refused,
so the other tests still find six projects and three clients.
"""

import re

from conftest import ADMIN_URL
from playwright.sync_api import expect

NAME_FIELD = "#field-name"
STATUS_NAME = "status"


def test_the_active_default_hides_finished_work_until_all_is_chosen(admin_page):
    admin_page.goto(f"{ADMIN_URL}/projects")
    expect(admin_page.get_by_role("cell", name="Apollo", exact=True)).to_be_visible()
    expect(admin_page.get_by_text("Cascade")).to_have_count(0)
    admin_page.click("button:has-text('Filters')")
    panel = admin_page.locator('[role="dialog"][aria-label="Filters"]')
    expect(panel).to_be_visible()
    panel.locator("div:has(> h3:text-is('Active'))").get_by_role("link", name="All").click()
    expect(admin_page.get_by_text("Cascade")).to_be_visible()


def test_a_duplicate_name_is_refused_on_the_form(admin_page):
    admin_page.goto(f"{ADMIN_URL}/projects/create")
    admin_page.fill(NAME_FIELD, "Apollo")
    admin_page.locator(f"[x-data*='adminSelect']:has(input[name='{STATUS_NAME}']) button").first.click()
    admin_page.get_by_role("option", name="planned").click()
    admin_page.click("button[type=submit][form=resource-form]")
    expect(admin_page.locator("[role=alert]").first).to_be_visible()
    expect(admin_page.locator(NAME_FIELD)).to_have_value("Apollo")
    expect(admin_page).to_have_url(re.compile(r"/projects/create$"))


def test_a_client_with_projects_cannot_be_deleted(admin_page):
    admin_page.goto(f"{ADMIN_URL}/clients/1/delete")
    admin_page.click("#delete-confirm")
    expect(admin_page).to_have_url(re.compile(r"/clients/1/delete$"))
    expect(admin_page.locator("body > ol[aria-label] > li")).to_have_count(1)
    admin_page.goto(f"{ADMIN_URL}/clients")
    expect(admin_page.get_by_role("cell", name="Northwind", exact=True)).to_be_visible()
