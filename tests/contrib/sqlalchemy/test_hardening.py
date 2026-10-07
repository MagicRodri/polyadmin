import asyncio
import warnings

import pytest
from sqlalchemy.exc import DataError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyadmin.core.query import ListRequest
from tests.contrib.sqlalchemy.models import Author, AuthorAdmin, make_session_factory, seed


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "db.sqlite")


class DeprecatingSession(AsyncSession):
    """Stands in for sqlmodel's AsyncSession, whose execute() warns."""

    async def execute(self, *args, **kwargs):
        warnings.warn("use exec()", DeprecationWarning, stacklevel=2)
        return await super().execute(*args, **kwargs)


def test_queries_bypass_a_subclass_execute_override(factory):
    seed(factory, Author(name="a"))
    sessions = async_sessionmaker(factory.kw["bind"], class_=DeprecatingSession)
    admin = AuthorAdmin(sessions)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        rows, total = asyncio.run(admin.list_page(ListRequest()))
        assert total == 1 and rows[0].name == "a"
        assert asyncio.run(admin.get_object("1")).name == "a"


class OverflowingSession(AsyncSession):
    """What asyncpg does with a pk outside int4."""

    async def get(self, *args, **kwargs):
        raise DataError("SELECT", {}, Exception("value out of int32 range"))


def test_a_pk_the_database_rejects_is_not_found(factory):
    sessions = async_sessionmaker(factory.kw["bind"], class_=OverflowingSession)
    assert asyncio.run(AuthorAdmin(sessions).get_object("99999999999")) is None


def test_default_filters_must_name_a_column():
    class Typo(AuthorAdmin):
        default_filters = {"is_delted": False}

    with pytest.raises(TypeError, match="is_delted"):
        Typo(lambda: None)
