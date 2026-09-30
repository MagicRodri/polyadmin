import re
import asyncio

import pytest
from sqlalchemy import event

from tests.sqlalchemy.models import Author, AuthorAdmin, Book, make_session_factory, seed


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "db.sqlite")


def test_bulk_update_fires_after_update_per_row(factory):
    seed(factory, Author(name="a"), Author(name="b"))
    admin = AuthorAdmin(factory)
    objects = [asyncio.run(admin.get_object(pk)) for pk in ("1", "2")]
    seen = []

    def listener(mapper, conn, target):
        seen.append(target.id)

    event.listen(Author, "after_update", listener)
    try:
        asyncio.run(admin.bulk_update(objects, {"nickname": "x"}, None))
    finally:
        event.remove(Author, "after_update", listener)
    assert sorted(seen) == [1, 2]


def test_bulk_delete_reports_how_far_it_got_on_integrity_error(factory):
    seed(factory, Author(name="free"), Author(name="referenced"))
    seed(factory, Book(title="b", author_id=2))
    admin = AuthorAdmin(factory)
    objects = [asyncio.run(admin.get_object(pk)) for pk in ("1", "2")]
    with pytest.raises(RuntimeError, match="Deleted 1 of 2"):
        asyncio.run(admin.delete_selected(objects, None))
    assert asyncio.run(admin.get_object("1")) is None
    assert asyncio.run(admin.get_object("2")) is not None


def _client(factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from polyadmin.core.admin import Admin
    from polyadmin.core.auth import AllowAllAuthenticator
    from polyadmin.fastapi.router import create_router

    admin = Admin(model_admins=[AuthorAdmin(factory)], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


@pytest.fixture
def referenced(factory):
    seed(factory, Author(name="free"), Author(name="referenced"))
    seed(factory, Book(title="b", author_id=2))
    return _client(factory)


def test_deleting_a_referenced_row_flashes_the_error_instead_of_a_500(referenced):
    from tests.conftest import csrf

    response = referenced.post("/admin/authors/2/delete", headers=csrf(referenced), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/authors/2/delete"
    page = referenced.get(response.headers["location"]).text
    assert 'data-level="error"' in page and "FOREIGN KEY" in page


def test_row_delete_of_a_referenced_row_does_not_500(referenced):
    from tests.conftest import csrf

    response = referenced.request("DELETE", "/admin/authors/2/delete", headers=csrf(referenced))
    assert response.status_code in (200, 303)
    assert referenced.get("/admin/authors/2").status_code == 200


def test_bulk_delete_failure_is_an_error_flash_with_progress(referenced):
    from tests.conftest import csrf

    response = referenced.post(
        "/admin/authors/actions/delete_selected",
        data={"pks": ["1", "2"], "_confirmed": "1"},
        headers=csrf(referenced),
        follow_redirects=False,
    )
    if response.status_code == 200:
        form = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', response.text))
        response = referenced.post(
            "/admin/authors/actions/delete_selected",
            data={**form, "pks": ["1", "2"]},
            headers=csrf(referenced),
            follow_redirects=False,
        )
    assert response.status_code == 303
    page = referenced.get(response.headers["location"]).text
    assert 'data-level="error"' in page
    assert "Deleted 1 of 2" in page
    assert "{&#39;&#39;" not in page and "{''" not in page
