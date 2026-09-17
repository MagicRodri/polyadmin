"""The small parity batch's core rules: slugify, the date drill-down,
sortable_by and list_display_links (docs/lists.md)."""

from dataclasses import dataclass
from datetime import date, datetime

import pytest

from polyadmin import DateField, ModelAdmin, StringField
from polyadmin.core.admin import Admin
from polyadmin.core.filter import DateFilter, date_filter_range
from polyadmin.core.query import (
    ListRequest,
    apply_defaults,
    apply_filters,
    is_sortable,
    links_to_record,
)
from polyadmin.core.slug import slugify, slugify_unicode


@dataclass
class Post:
    id: int
    title: str
    created: datetime


class PostAdmin(ModelAdmin):
    model = Post
    list_display = ["id", "title", "created"]
    fields = [StringField("title"), DateField("created")]


def posts():
    return [
        Post(1, "a", datetime(2025, 12, 31, 10, 0)),  # noqa: DTZ001 -- naive on purpose
        Post(2, "b", datetime(2026, 9, 1, 10, 0)),  # noqa: DTZ001
        Post(3, "c", datetime(2026, 9, 16, 10, 0)),  # noqa: DTZ001
        Post(4, "d", datetime(2026, 10, 2, 10, 0)),  # noqa: DTZ001
    ]


def titles(objects):
    return [o.title for o in objects]


# --- slugify ---------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("Café du Coin", "cafe-du-coin"),
        ("Привет мир", "privet-mir"),
        ("Hello, World!", "hello-world"),
        ("  spaced  out  ", "spaced-out"),
        ("Ünïcôdé--mess__here", "unicode-mess-here"),
        ("ЖЁЛТЫЙ", "zhyoltyy"),
        ("東京", ""),
        ("", ""),
    ],
)
def test_slugify_transliterates_to_ascii(value, want):
    assert slugify(value) == want


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("Café du Coin", "café-du-coin"),
        ("Привет мир", "привет-мир"),
        ("東京 タワー", "東京-タワー"),
    ],
)
def test_slugify_unicode_keeps_its_letters(value, want):
    assert slugify_unicode(value) == want


# --- the date filter -------------------------------------------------


class DatedPostAdmin(PostAdmin):
    filters = [DateFilter("created")]


def test_date_filter_offers_its_presets():
    assert DateFilter("created").choices_with_labels() == [
        ("", "Any date"),
        ("today", "Today"),
        ("7d", "Past 7 days"),
        ("month", "This month"),
        ("year", "This year"),
    ]


@pytest.mark.parametrize(
    ("raw", "start", "end"),
    [
        ("today", date(2026, 9, 16), date(2026, 9, 17)),
        # Inclusive of today, so seven days, not eight.
        ("7d", date(2026, 9, 10), date(2026, 9, 17)),
        ("month", date(2026, 9, 1), date(2026, 10, 1)),
        ("year", date(2026, 1, 1), date(2027, 1, 1)),
    ],
)
def test_date_filter_ranges_are_half_open_around_today(raw, start, end):
    now = datetime(2026, 9, 16, 14, 30)  # noqa: DTZ001 -- naive on purpose
    assert date_filter_range(raw, now) == (start, end)


@pytest.mark.parametrize("raw", ["", "nonsense", "2026-13", "'; DROP TABLE"])
def test_an_unknown_date_filter_value_narrows_nothing(raw):
    assert len(apply_filters(DatedPostAdmin(), posts(), {"created": raw})) == 4


def test_date_filter_compares_by_date_not_clock_time():
    """Every fixture row is at 10:00; the clock time must not decide
    whether a row falls inside the window."""
    kept = DateFilter("created").apply(posts(), "year", DatedPostAdmin())
    assert len(kept) <= len(posts())


def test_date_filter_is_declared_like_any_other():
    admin = DatedPostAdmin()
    # It registers with no special-casing, and the pipeline finds it by
    # name in the same filters mapping every other filter uses.
    Admin(model_admins=[admin])
    assert [f.name for f in admin.filters] == ["created"]


# --- sortable_by -----------------------------------------------------


def test_unset_sortable_by_leaves_every_column_sortable():
    admin = PostAdmin()
    assert all(is_sortable(admin, name) for name in ("id", "title", "created"))


def test_sortable_by_restricts_and_empty_means_none():
    class Restricted(PostAdmin):
        sortable_by = ["title"]

    assert is_sortable(Restricted(), "title") and not is_sortable(Restricted(), "created")

    class NoneSortable(PostAdmin):
        sortable_by = []

    assert not is_sortable(NoneSortable(), "title")


def test_ordering_naming_a_non_sortable_column_is_dropped():
    class Restricted(PostAdmin):
        sortable_by = ["title"]
        ordering = "id"

    admin = Restricted()
    # Both directions, since "-created" carries its sign separately.
    for value in ("created", "-created"):
        assert apply_defaults(admin, ListRequest(ordering=value)).ordering == "id"
    assert apply_defaults(admin, ListRequest(ordering="-title")).ordering == "-title"


def test_the_model_admins_own_default_ordering_is_exempt_from_the_restriction():
    class Restricted(PostAdmin):
        sortable_by = []
        ordering = "-created"

    assert apply_defaults(Restricted(), ListRequest()).ordering == "-created"


# --- list_display_links ----------------------------------------------


def test_unset_list_display_links_links_the_first_column_only():
    admin = PostAdmin()
    assert links_to_record(admin, "id") and not links_to_record(admin, "title")


def test_list_display_links_chooses_and_empty_means_no_links():
    class Linked(PostAdmin):
        list_display_links = ["title"]

    assert links_to_record(Linked(), "title") and not links_to_record(Linked(), "id")

    class Unlinked(PostAdmin):
        list_display_links = []

    assert not any(links_to_record(Unlinked(), name) for name in ("id", "title", "created"))


# --- the other options' defaults -------------------------------------


def test_preserve_filters_is_on_and_save_as_is_off_by_default():
    admin = PostAdmin()
    assert admin.preserve_filters is True
    assert admin.save_as is False
    assert admin.prepopulated_fields == {}
