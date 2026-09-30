import asyncio
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.core.model_admin import RecordFormError
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.sqlalchemy.models import Author, AuthorAdmin, BookAdmin, Kind, make_session_factory, seed


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "db.sqlite")


def test_create_coerces_form_strings(factory):
    author = asyncio.run(
        AuthorAdmin(factory).create(
            {
                "name": "Tolstoy",
                "active": True,
                "kind": "science",
                "born": "1828-09-09",
                "nickname": None,
                "created": "2026-09-30T10:00:00",
            }
        )
    )
    assert author.id is not None
    assert author.kind is Kind.SCIENCE and author.born == date(1828, 9, 9)


def test_create_sets_the_fk_from_a_relation_field(factory):
    seed(factory, Author(name="Tolstoy"))
    book = asyncio.run(BookAdmin(factory).create({"title": "War and Peace", "author": "1"}))
    assert book.author_id == 1 and book.author.name == "Tolstoy"


def test_get_object_returns_none_for_missing_or_unparsable_pk(factory):
    admin = AuthorAdmin(factory)
    assert asyncio.run(admin.get_object("999")) is None
    assert asyncio.run(admin.get_object("abc")) is None


def test_update_changes_only_given_fields_and_fires_after_update(factory):
    seed(factory, Author(name="Tolstoy", nickname="Leo"))
    seen = []

    def listener(mapper, conn, target):
        seen.append(target.name)

    event.listen(Author, "after_update", listener)
    try:
        admin = AuthorAdmin(factory)
        obj = asyncio.run(admin.get_object("1"))
        updated = asyncio.run(admin.update(obj, {"name": "L. Tolstoy"}))
    finally:
        event.remove(Author, "after_update", listener)
    assert updated.name == "L. Tolstoy" and updated.nickname == "Leo"
    assert seen == ["L. Tolstoy"]


def test_delete_goes_through_the_orm(factory):
    seed(factory, Author(name="Tolstoy"))
    seen = []

    def listener(mapper, conn, target):
        seen.append(target.id)

    event.listen(Author, "after_delete", listener)
    try:
        admin = AuthorAdmin(factory)
        asyncio.run(admin.delete(asyncio.run(admin.get_object("1"))))
    finally:
        event.remove(Author, "after_delete", listener)
    assert seen == [1]
    assert asyncio.run(admin.get_object("1")) is None


def test_unique_violation_becomes_a_record_form_error(factory):
    seed(factory, Author(name="Tolstoy"))
    with pytest.raises(RecordFormError) as info:
        asyncio.run(AuthorAdmin(factory).create({"name": "Tolstoy"}))
    assert info.value.errors[""]


def test_bad_value_becomes_a_field_error(factory):
    with pytest.raises(RecordFormError) as info:
        asyncio.run(AuthorAdmin(factory).create({"name": "X", "born": "not-a-date"}))
    assert "born" in info.value.errors


def _client(factory):
    admin = Admin(model_admins=[AuthorAdmin(factory), BookAdmin(factory)], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_detail_of_unparsable_pk_is_404(factory):
    assert _client(factory).get("/admin/authors/abc").status_code == 404


def test_end_to_end_list_create_and_duplicate(factory):
    client = _client(factory)
    created = client.post(
        "/admin/authors/create",
        data={"name": "Tolstoy", "kind": "fiction"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert created.status_code in (302, 303)
    assert "Tolstoy" in client.get("/admin/authors").text
    duplicate = client.post("/admin/authors/create", data={"name": "Tolstoy", "kind": "fiction"}, headers=csrf(client))
    assert duplicate.status_code == 422
