import asyncio

import pytest

from polyadmin.core.field import BooleanField, DateField, DateTimeField, EnumField, IntegerField, StringField
from polyadmin.core.query import ListRequest
from tests.contrib.sqlalchemy.models import Author, AuthorAdmin, Book, BookAdmin, make_session_factory, seed


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "db.sqlite")


def _names(rows):
    return [row.name for row in rows]


def test_list_page_pages_and_counts_everything(factory):
    seed(factory, *[Author(name=f"a{i:02d}") for i in range(30)])
    rows, total = asyncio.run(AuthorAdmin(factory).list_page(ListRequest(page=2, page_size=10)))
    assert total == 30
    assert _names(rows) == [f"a{i:02d}" for i in range(10, 20)]


def test_unlimited_returns_every_row(factory):
    seed(factory, *[Author(name=f"a{i:02d}") for i in range(30)])
    rows, total = asyncio.run(AuthorAdmin(factory).list_page(ListRequest(unlimited=True)))
    assert total == 30 and len(rows) == 30


def test_search_is_case_insensitive_over_every_search_field(factory):
    seed(factory, Author(name="Tolstoy"), Author(name="Gogol", nickname="tolstoy-fan"), Author(name="Pushkin"))
    rows, total = asyncio.run(AuthorAdmin(factory).list_page(ListRequest(search="TOLSTOY")))
    assert total == 2
    assert sorted(_names(rows)) == ["Gogol", "Tolstoy"]


def test_search_matches_wildcards_literally(factory):
    seed(factory, Author(name="100% true"), Author(name="1000 true"), Author(name="a_b"), Author(name="axb"))
    admin = AuthorAdmin(factory)
    assert _names(asyncio.run(admin.list_page(ListRequest(search="100%")))[0]) == ["100% true"]
    assert _names(asyncio.run(admin.list_page(ListRequest(search="a_b")))[0]) == ["a_b"]


def test_ordering_descending_then_pk(factory):
    seed(factory, Author(name="b"), Author(name="a"), Author(name="c"))
    rows, _ = asyncio.run(AuthorAdmin(factory).list_page(ListRequest(ordering="-name")))
    assert _names(rows) == ["c", "b", "a"]


def test_unknown_ordering_falls_back_to_pk(factory):
    seed(factory, Author(name="b"), Author(name="a"))
    rows, _ = asyncio.run(AuthorAdmin(factory).list_page(ListRequest(ordering="nope")))
    assert _names(rows) == ["b", "a"]


class ActiveOnlyAuthorAdmin(AuthorAdmin):
    default_filters = {"active": True}


def test_default_filters_apply_until_the_filter_is_chosen(factory):
    seed(factory, Author(name="on", active=True), Author(name="off", active=False))
    admin = ActiveOnlyAuthorAdmin(factory)
    assert _names(asyncio.run(admin.list_page(ListRequest()))[0]) == ["on"]
    assert _names(asyncio.run(admin.list_page(ListRequest(filters={"active": "false"})))[0]) == ["off"]
    assert sorted(_names(asyncio.run(admin.list_page(ListRequest(filters={"active": ""})))[0])) == ["off", "on"]


def test_relationships_in_list_display_are_eager_loaded(factory):
    author = Author(name="Tolstoy")
    seed(factory, Book(title="War and Peace", author=author))
    rows, _ = asyncio.run(BookAdmin(factory).list_page(ListRequest()))
    assert rows[0].author.name == "Tolstoy"


def test_fields_are_derived_from_columns():
    fields = AuthorAdmin(lambda: None).get_fields()
    assert isinstance(fields["id"], IntegerField)
    assert isinstance(fields["name"], StringField) and fields["name"].required
    assert isinstance(fields["active"], BooleanField)
    assert isinstance(fields["born"], DateField)
    assert isinstance(fields["created"], DateTimeField)
    assert isinstance(fields["kind"], EnumField)
    assert not fields["nickname"].required


def test_missing_session_factory_is_a_type_error():
    with pytest.raises(TypeError, match="session_factory"):
        AuthorAdmin()
