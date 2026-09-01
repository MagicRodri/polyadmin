from polyadmin.core.filter import BooleanFilter
from polyadmin.core.query import DEFAULT_PAGE_SIZE, ListRequest, execute_list_query
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


# -- the ListQuerier capability ------------------------------------------


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
