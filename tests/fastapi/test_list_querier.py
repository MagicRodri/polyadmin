"""The optional list_page capability -- mirrors go-polyadmin/fiber/listquerier_test.go."""
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.query import ListRequest
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


class QueryingUserAdmin(InMemoryUserAdmin):
    """Implements list_page. Records what it was asked for and returns a
    fixed page, so the tests can assert both that the framework
    delegated and that it left the result alone.

    get_queryset deliberately returns a sentinel row that must never
    reach a page: if the framework fell back to the in-memory path, that
    row would show up and the assertions would fail loudly rather than
    silently passing for the wrong reason.
    """

    def __init__(self):
        super().__init__()
        self.calls = []
        self.queryset_calls = 0
        self.total = 137
        self._rows = [self._make(1, "from-the-querier@example.com")]

    def _make(self, pk, email):
        obj = type("Row", (), {})()
        obj.id, obj.email, obj.is_active = pk, email, True
        return obj

    def get_queryset(self):
        self.queryset_calls += 1
        return [self._make(99, "IN-MEMORY-FALLBACK@example.com")]

    def list_page(self, list_request):
        self.calls.append(list_request)
        return self._rows, self.total


def querying_client():
    ma = QueryingUserAdmin()
    admin = Admin(model_admins=[ma])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), ma


def test_list_querier_is_used_instead_of_the_in_memory_path():
    client, ma = querying_client()
    page = client.get("/admin/users?search=anything&page=3&page_size=10").text

    assert len(ma.calls) == 1, f"expected exactly one list_page call, got {len(ma.calls)}"
    assert ma.queryset_calls == 0, "get_queryset must not be called when list_page handles the query"
    assert "from-the-querier@example.com" in page
    assert "IN-MEMORY-FALLBACK" not in page, "the framework fell back to filtering in memory"


def test_list_querier_receives_the_whole_request():
    client, ma = querying_client()
    client.get("/admin/users?search=jane&sort=-email&page=3&page_size=10&filter[is_active]=true")

    got = ma.calls[0]
    assert got.search == "jane"
    assert got.ordering == "-email"
    assert got.filters.get("is_active") == "true"
    assert got.window() == (20, 10)


def test_list_querier_total_drives_pagination():
    # The count the querier reports is what pagination believes -- the
    # whole point of returning it separately from the rows.
    client, ma = querying_client()
    page = client.get("/admin/users?page_size=10").text
    assert str(ma.total) in page


def test_export_asks_the_querier_for_everything():
    client, ma = querying_client()
    client.get("/admin/users/export/csv?page=4&page_size=10&search=jane")

    got = ma.calls[0]
    assert got.unlimited, "an export must ask for every matching row"
    assert got.window() == (0, 0), "no page window on an export"
    assert got.search == "jane", "the export must keep the filters the user was looking at"


def test_lookup_asks_the_querier_for_a_capped_page():
    from polyadmin.fastapi.handlers import LOOKUP_LIMIT

    client, ma = querying_client()
    client.get("/admin/users/lookup?q=jan")

    got = ma.calls[0]
    assert got.search == "jan"
    assert got.window()[1] == LOOKUP_LIMIT


def test_admin_without_list_page_still_paginates_in_memory():
    # Both requests pin an explicit sort. The fixture stores rows in a
    # dict and the framework has no default ordering, so without one the
    # comparison would not be stable. (That missing default ordering is
    # a real gap; see the roadmap.)
    user_admin = InMemoryUserAdmin()
    for i in range(25):
        user_admin.create({"email": f"user{i}@example.com"})
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    pattern = re.compile(r"user\d+@example\.com")

    def emails_on(path):
        return set(pattern.findall(client.get(path).text))

    first = emails_on("/admin/users?sort=email&page=1&page_size=10")
    second = emails_on("/admin/users?sort=email&page=2&page_size=10")

    assert len(first) == 10 and len(second) == 10
    assert not (first & second), "a row appears on both pages -- the window is not advancing"
