"""list_per_page, empty_value_display, and "Save and add another"."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.query import DEFAULT_EMPTY_VALUE, DEFAULT_PAGE_SIZE
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin, User


def _client(model_admin):
    admin = Admin(model_admins=[model_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app, follow_redirects=False)


def _paged_admin(rows, per_page):
    class Paged(InMemoryUserAdmin):
        list_per_page = per_page
        # A stable order, or "the first page" is not a well-defined set.
        ordering = "email"

    a = Paged()
    a._store = {i: User(id=i, email=f"u{1000 + i}@example.com") for i in range(1, rows + 1)}
    a._next_id = rows + 1
    return a


def _count_rows(page):
    # One <tr> per record plus the header row.
    return page.count("<tr") - 1


def test_list_per_page_is_honoured_when_the_request_names_no_size():
    page = _client(_paged_admin(30, 5)).get("/admin/users").text
    assert _count_rows(page) == 5


def test_list_per_page_beats_the_framework_default():
    page = _client(_paged_admin(30, 5)).get("/admin/users").text
    assert _count_rows(page) != DEFAULT_PAGE_SIZE


def test_pager_reflects_the_model_admins_page_size():
    page = _client(_paged_admin(30, 5)).get("/admin/users").text
    # Matched against the pager's own sentence (ui/pagination.html), not
    # a bare "6" that could come from anywhere on the page: 30 rows at 5
    # per page is 6 pages, where the old unresolved request gave 2.
    match = re.search(r"Page\s+1\s+of\s+(\d+)", page)
    assert match, "no pager on the page"
    assert match.group(1) == "6", "pager was sized from the unresolved request"


def test_explicit_page_size_beats_the_model_admins_default():
    page = _client(_paged_admin(30, 5)).get("/admin/users?page_size=10").text
    assert _count_rows(page) == 10


def test_without_a_list_per_page_the_framework_default_applies():
    page = _client(_paged_admin(30, None)).get("/admin/users").text
    assert _count_rows(page) == DEFAULT_PAGE_SIZE


def _one_user_client(email="", **kwargs):
    a = InMemoryUserAdmin()
    a._store = {1: User(id=1, email=email, **kwargs)}
    a._next_id = 2
    return _client(a), a


def test_blank_value_shows_the_placeholder():
    client, _ = _one_user_client(email="")
    assert DEFAULT_EMPTY_VALUE in client.get("/admin/users/1").text


def test_empty_value_display_is_configurable():
    class Custom(InMemoryUserAdmin):
        empty_value_display = "not set"

    a = Custom()
    a._store = {1: User(id=1, email="")}
    a._next_id = 2
    assert "not set" in _client(a).get("/admin/users/1").text


def test_zero_and_false_are_not_treated_as_empty():
    a = InMemoryUserAdmin()
    a._store = {0: User(id=0, email="someone@example.com", is_active=False)}
    a._next_id = 1
    assert DEFAULT_EMPTY_VALUE not in _client(a).get("/admin/users/0").text


def test_empty_value_display_is_escaped():
    class Injected(InMemoryUserAdmin):
        empty_value_display = "<script>alert(1)</script>"

    a = Injected()
    a._store = {1: User(id=1, email="")}
    a._next_id = 2
    assert "<script>alert(1)</script>" not in _client(a).get("/admin/users/1").text


def test_save_and_add_another_returns_to_an_empty_form():
    a = InMemoryUserAdmin()
    client = _client(a)
    response = client.post(
        "/admin/users/create",
        data={"email": "first@example.com", "_addanother": "1"},
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/users/create")


def test_save_and_add_another_still_creates_the_record():
    a = InMemoryUserAdmin()
    client = _client(a)
    client.post(
        "/admin/users/create",
        data={"email": "first@example.com", "_addanother": "1"},
        headers=csrf(client),
    )
    assert any(u.email == "first@example.com" for u in a.get_queryset())


def test_plain_save_still_goes_to_the_record():
    a = InMemoryUserAdmin()
    client = _client(a)
    response = client.post(
        "/admin/users/create", data={"email": "first@example.com"}, headers=csrf(client)
    )
    location = response.headers["location"]
    assert not location.endswith("/create")
    assert not location.endswith("/edit")


def test_the_button_is_offered_on_the_form():
    assert 'name="_addanother"' in _client(InMemoryUserAdmin()).get("/admin/users/create").text
