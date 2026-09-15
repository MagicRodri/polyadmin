import asyncio

from polyadmin.core.field import StringField
from polyadmin.core.filter import BooleanFilter
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.query import (
    DEFAULT_PAGE_SIZE,
    ListRequest,
    alist_objects,
    execute_list_query,
    list_objects,
)
from tests.core.test_model_admin import InMemoryUserAdmin


def make_admin_with_filter():
    class FilterableUserAdmin(InMemoryUserAdmin):
        filters = [BooleanFilter("is_active")]

    return FilterableUserAdmin()


def test_search_matches_search_fields_case_insensitively():
    admin = InMemoryUserAdmin()
    john = admin.create({"email": "John@Example.com"})
    admin.create({"email": "mary@example.com"})

    result = execute_list_query(admin, admin.get_queryset(), ListRequest(search="john"))
    assert result == [john]


def test_search_empty_is_noop():
    admin = InMemoryUserAdmin()
    admin.create({"email": "john@example.com"})
    result = execute_list_query(admin, admin.get_queryset(), ListRequest())
    assert result == admin.get_queryset()


def test_filters_applied_by_name():
    admin = make_admin_with_filter()
    active = admin.create({"email": "a@example.com", "is_active": True})
    admin.create({"email": "b@example.com", "is_active": False})

    result = execute_list_query(admin, admin.get_queryset(), ListRequest(filters={"is_active": "true"}))
    assert result == [active]


def test_ordering_ascending_and_descending():
    admin = InMemoryUserAdmin()
    b = admin.create({"email": "b@example.com"})
    a = admin.create({"email": "a@example.com"})

    asc = execute_list_query(admin, admin.get_queryset(), ListRequest(ordering="email"))
    assert asc == [a, b]

    desc = execute_list_query(admin, admin.get_queryset(), ListRequest(ordering="-email"))
    assert desc == [b, a]


def test_ordering_unknown_field_is_noop():
    admin = InMemoryUserAdmin()
    admin.create({"email": "a@example.com"})
    result = execute_list_query(admin, admin.get_queryset(), ListRequest(ordering="nope"))
    assert result == admin.get_queryset()


def test_search_filter_ordering_compose():
    admin = make_admin_with_filter()
    admin.create({"email": "zzz@example.com", "is_active": False})
    match1 = admin.create({"email": "match-b@example.com", "is_active": True})
    match2 = admin.create({"email": "match-a@example.com", "is_active": True})

    result = execute_list_query(
        admin,
        admin.get_queryset(),
        ListRequest(search="match", filters={"is_active": "true"}, ordering="email"),
    )
    assert result == [match2, match1]


def test_list_window_derives_offset_and_limit_from_the_page():
    cases = [
        (ListRequest(page=1, page_size=25), (0, 25)),
        (ListRequest(page=3, page_size=10), (20, 10)),
        # Unset is "the first page of the default size".
        (ListRequest(), (0, DEFAULT_PAGE_SIZE)),
        # unlimited is how export asks for every matching row.
        (ListRequest(unlimited=True), (0, 0)),
    ]
    for request, expected in cases:
        assert request.window() == expected, request


def test_unlimited_window_ignores_the_page_number():
    # "Every matching row" cannot also be "starting from row 40" -- an
    # export of a filtered set is the whole set, whichever page the user
    # happened to be looking at when they clicked Export.
    assert ListRequest(page=5, page_size=10, unlimited=True).window() == (0, 0)


class _Row:
    def __init__(self, name):
        self.name = name


def _ordered_admin(ordering):
    class A(ModelAdmin):
        model = _Row
        list_display = ["name"]
        fields = [StringField("name")]

        def get_queryset(self):
            return [_Row("charlie"), _Row("alpha"), _Row("bravo")]

    A.ordering = ordering
    return A()


def _names(objects):
    return ",".join(o.name for o in objects)


def test_default_ordering_applies_when_the_request_names_none():
    objects, _ = list_objects(_ordered_admin("name"), ListRequest(unlimited=True))
    assert _names(objects) == "alpha,bravo,charlie"


def test_an_explicit_sort_beats_the_default():
    objects, _ = list_objects(_ordered_admin("name"), ListRequest(ordering="-name", unlimited=True))
    assert _names(objects) == "charlie,bravo,alpha", "the user's own sort must win"


def test_no_default_ordering_leaves_the_source_order_alone():
    objects, _ = list_objects(_ordered_admin(None), ListRequest(unlimited=True))
    assert _names(objects) == "charlie,alpha,bravo"


class AsyncListPageUserAdmin(InMemoryUserAdmin):
    """A list_page that is itself a coroutine function, and a get_queryset
    that must never run when list_page is present -- same contract as the
    sync QueryingUserAdmin in tests/fastapi/test_list_querier.py."""

    def __init__(self):
        super().__init__()
        self.queryset_calls = 0
        self._rows = [self.create({"email": "async-page@example.com"})]

    def get_queryset(self):
        self.queryset_calls += 1
        return [self.create({"email": "SHOULD-NOT-APPEAR@example.com"})]

    async def list_page(self, list_request):
        await asyncio.sleep(0)
        return self._rows, 1


def test_alist_objects_awaits_an_async_list_page():
    admin = AsyncListPageUserAdmin()
    rows, total = asyncio.run(alist_objects(admin, ListRequest()))
    assert rows == admin._rows
    assert total == 1
    assert admin.queryset_calls == 0


class AsyncQuerysetUserAdmin(InMemoryUserAdmin):
    """No list_page: get_queryset itself is the coroutine function, so the
    in-memory search/filter/order/paginate tail still runs on its result."""

    async def get_queryset(self):
        await asyncio.sleep(0)
        return list(self._store.values())


def test_alist_objects_awaits_an_async_get_queryset_then_paginates_in_memory():
    admin = AsyncQuerysetUserAdmin()
    admin.create({"email": "b@example.com"})
    admin.create({"email": "a@example.com"})

    rows, total = asyncio.run(alist_objects(admin, ListRequest(ordering="email")))
    assert [r.email for r in rows] == ["a@example.com", "b@example.com"]
    assert total == 2


def test_alist_objects_still_works_with_fully_sync_hooks():
    """Backward compatibility: a plain sync ModelAdmin behaves identically
    through alist_objects as through list_objects."""
    admin = InMemoryUserAdmin()
    admin.create({"email": "john@example.com"})

    sync_rows, sync_total = list_objects(admin, ListRequest())
    async_rows, async_total = asyncio.run(alist_objects(admin, ListRequest()))
    assert async_rows == sync_rows
    assert async_total == sync_total
