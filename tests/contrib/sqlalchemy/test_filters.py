import asyncio
from datetime import date, timedelta

import pytest

from polyadmin.core.filter import Filter
from polyadmin.core.query import ListRequest
from tests.contrib.sqlalchemy.models import Author, AuthorAdmin, Book, BookAdmin, Kind, make_session_factory, seed


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "db.sqlite")


def _names(admin, **filters):
    rows, _ = asyncio.run(admin.list_page(ListRequest(filters=filters)))
    return sorted(row.name for row in rows)


def test_boolean_filter_false_includes_null(factory):
    seed(factory, Author(name="on", active=True), Author(name="off", active=False), Author(name="unknown", active=None))
    admin = AuthorAdmin(factory)
    assert _names(admin, active="true") == ["on"]
    assert _names(admin, active="false") == ["off", "unknown"]


def test_choice_filter_coerces_to_the_enum(factory):
    seed(factory, Author(name="f", kind=Kind.FICTION), Author(name="s", kind=Kind.SCIENCE))
    assert _names(AuthorAdmin(factory), kind="science") == ["s"]


def test_choice_filter_with_an_uncoercible_value_matches_nothing(factory):
    seed(factory, Author(name="f", kind=Kind.FICTION))
    assert _names(AuthorAdmin(factory), kind="bogus") == []


def test_empty_filter_treats_blank_strings_as_empty(factory):
    seed(factory, Author(name="none"), Author(name="blank", nickname=""), Author(name="set", nickname="x"))
    admin = AuthorAdmin(factory)
    assert _names(admin, nickname="empty") == ["blank", "none"]
    assert _names(admin, nickname="notempty") == ["set"]


def test_date_filter_uses_the_half_open_window(factory):
    today = date.today()
    seed(factory, Author(name="today", born=today), Author(name="old", born=today - timedelta(days=400)))
    assert _names(AuthorAdmin(factory), born="today") == ["today"]


def test_relation_filter_narrows_by_the_related_pk(factory):
    tolstoy, gogol = Author(name="Tolstoy"), Author(name="Gogol")
    seed(factory, Book(title="War and Peace", author=tolstoy), Book(title="Dead Souls", author=gogol))
    rows, _ = asyncio.run(BookAdmin(factory).list_page(ListRequest(filters={"author": "1"})))
    assert [row.title for row in rows] == ["War and Peace"]


def test_relation_filter_with_a_non_numeric_pk_matches_nothing(factory):
    seed(factory, Book(title="War and Peace", author=Author(name="Tolstoy")))
    rows, _ = asyncio.run(BookAdmin(factory).list_page(ListRequest(filters={"author": "abc"})))
    assert rows == []


class CustomFilter(Filter):
    def choices_with_labels(self):
        return [("", "All")]


def test_untranslatable_filter_fails_at_construction():
    class Broken(AuthorAdmin):
        filters = (CustomFilter("name"),)

    with pytest.raises(TypeError, match="no SQL translation"):
        Broken(lambda: None)
