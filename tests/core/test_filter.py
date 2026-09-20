from datetime import date, datetime

import pytest

from polyadmin.core.field import ForeignKeyField, ManyToManyField, StringField
from polyadmin.core.filter import (
    DATE_FILTER_PAST_7_DAYS,
    DATE_FILTER_TODAY,
    EMPTY_FILTER_EMPTY,
    EMPTY_FILTER_NOT_EMPTY,
    FILTER_KIND_DATE_RANGE,
    FILTER_KIND_RELATION,
    BooleanFilter,
    ChoiceFilter,
    DateFilter,
    EmptyFilter,
    RelationFilter,
    date_filter_range,
    date_filter_range_values,
    is_empty_value,
)
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.query import fold_range_params
from polyadmin.core.relation import MANY, ONE, Relation
from tests.core.test_model_admin import InMemoryUserAdmin, User


def test_boolean_filter_true():
    admin = InMemoryUserAdmin()
    active = admin.create({"email": "a@example.com", "is_active": True})
    admin.create({"email": "b@example.com", "is_active": False})

    filt = BooleanFilter("is_active")
    result = filt.apply(admin.get_queryset(), "true", admin)
    assert result == [active]


def test_boolean_filter_empty_value_is_noop():
    admin = InMemoryUserAdmin()
    admin.create({"email": "a@example.com", "is_active": True})
    admin.create({"email": "b@example.com", "is_active": False})

    filt = BooleanFilter("is_active")
    assert filt.apply(admin.get_queryset(), "", admin) == admin.get_queryset()


def test_boolean_filter_choices():
    filt = BooleanFilter("is_active")
    assert filt.choices_with_labels() == [("", "All"), ("true", "Yes"), ("false", "No")]


class RoleUser:
    def __init__(self, role):
        self.role = role


class RoleAdmin(ModelAdmin):
    model = User
    fields = [StringField("role")]


def test_choice_filter():
    role_admin = RoleAdmin()
    objects = [RoleUser("admin"), RoleUser("member")]

    filt = ChoiceFilter("role", choices=["admin", "member"])
    result = filt.apply(objects, "admin", role_admin)

    assert len(result) == 1 and result[0].role == "admin"
    assert filt.choices_with_labels() == [("", "All"), ("admin", "admin"), ("member", "member")]


@pytest.mark.parametrize(
    ("value", "empty"),
    [
        (None, True),
        ("", True),
        ([], True),
        ({}, True),
        (datetime.min, True),  # noqa: DTZ901 -- a sentinel, see is_empty_value
        (0, False),
        (False, False),
        ("0", False),
        ("hi", False),
    ],
)
def test_zero_is_a_value_not_an_absence(value, empty):
    """The whole semantic decision in one test: somebody chose 0 and
    False, so neither is empty."""
    assert is_empty_value(value) is empty


def test_empty_filter_keeps_only_blanks():
    admin = InMemoryUserAdmin()
    blank = admin.create({"email": ""})
    filled = admin.create({"email": "a@example.com"})
    objects = admin.get_queryset()

    filt = EmptyFilter("email")
    assert filt.apply(objects, EMPTY_FILTER_EMPTY, admin) == [blank]
    assert filt.apply(objects, EMPTY_FILTER_NOT_EMPTY, admin) == [filled]
    # An unrecognised value narrows nothing, as every other filter does.
    assert filt.apply(objects, "nonsense", admin) == objects
    assert filt.apply(objects, "", admin) == objects


def test_empty_filter_offers_its_three_choices():
    assert EmptyFilter("notes").choices_with_labels() == [
        ("", "All"),
        (EMPTY_FILTER_EMPTY, "Empty"),
        (EMPTY_FILTER_NOT_EMPTY, "Not empty"),
    ]


def test_a_filter_without_a_control_kind_is_a_choice_list():
    """The capability is optional, so every filter that existed before
    this change keeps rendering as it did."""
    for filt in (BooleanFilter("flag"), ChoiceFilter("notes", choices=["a"]), EmptyFilter("notes")):
        assert filt.control_kind == "", f"{type(filt).__name__} declares a control kind"


def test_a_custom_range_is_inclusive_of_both_ends():
    now = datetime(2026, 3, 15, 9, 30)  # noqa: DTZ001 -- the reader's own day
    window = date_filter_range("2026-01-01:2026-03-01", now)
    assert window is not None, "a well-formed range was rejected"
    start, end = window
    assert start == date(2026, 1, 1)
    # Half-open internally, so the inclusive end is the following day.
    assert end == date(2026, 3, 2)


def test_an_empty_range_end_means_through_today():
    """Resolved by the parser, not the UI: the JS-off form posts the
    blank, and a value the parser then rejected would break exactly the
    path the panel's links exist to protect."""
    now = datetime(2026, 3, 15, 9, 30)  # noqa: DTZ001
    assert date_filter_range("2026-01-01:", now) == (date(2026, 1, 1), date(2026, 3, 16))


@pytest.mark.parametrize(
    "raw",
    [
        ":2026-03-01",            # no start: unbounded-below has no natural resolution
        "2026-03-01:2026-01-01",  # end before start
        "nonsense:2026-03-01",    # unparseable start
        "2026-01-01:nonsense",    # unparseable end
        "2026-01-01",             # no separator: not a range, not a preset
        "01/01/2026:01/03/2026",  # wrong format
    ],
)
def test_a_malformed_range_narrows_nothing(raw):
    assert date_filter_range(raw, datetime(2026, 3, 15, 9, 30)) is None  # noqa: DTZ001


def test_the_range_values_come_back_for_prefilling():
    assert date_filter_range_values("2026-01-01:2026-03-01") == ("2026-01-01", "2026-03-01")
    assert date_filter_range_values(DATE_FILTER_PAST_7_DAYS) is None


def test_date_filter_declares_the_range_control():
    assert DateFilter("founded").control_kind == FILTER_KIND_DATE_RANGE


def test_the_range_and_the_presets_share_one_parser():
    """The property step 3 was built around: one parser means the
    in-memory path and a list_page host cannot disagree."""
    now = datetime(2026, 3, 15, 9, 30)  # noqa: DTZ001
    assert date_filter_range(DATE_FILTER_TODAY, now) == date_filter_range("2026-03-15:2026-03-15", now)


def test_the_range_form_folds_into_one_filter_value():
    """The panel's two date inputs cannot produce one parameter on their
    own, so the route folds them. Folding server-side rather than in JS
    is what keeps the range working with scripting off."""
    admin = InMemoryUserAdmin()
    admin.filters = [DateFilter("joined")]
    filters = {"other": "kept"}
    fold_range_params(admin, filters, "joined", "2026-01-01", "2026-03-01")
    assert filters["joined"] == "2026-01-01:2026-03-01"
    assert filters["other"] == "kept", "folding clobbered another filter"


def test_the_range_form_ignores_an_undeclared_filter():
    # _range_for arrives from the client, so it names a filter only if the
    # ModelAdmin declared one -- otherwise a crafted form could inject any
    # key into filters.
    admin = InMemoryUserAdmin()
    admin.filters = [DateFilter("joined")]
    filters = {}
    fold_range_params(admin, filters, "sneaky", "2026-01-01", "2026-03-01")
    assert filters == {}


def test_an_empty_range_form_clears_the_filter():
    admin = InMemoryUserAdmin()
    admin.filters = [DateFilter("joined")]
    filters = {"joined": "7d"}
    fold_range_params(admin, filters, "joined", "", "")
    assert "joined" not in filters


class Target:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Row:
    def __init__(self, id, org=None, teams=None):
        self.id = id
        self.org = org
        self.teams = teams if teams is not None else []


class RowAdmin(ModelAdmin):
    model = Row
    list_display = ["id", "org"]
    fields = [
        ForeignKeyField(
            "org", relation=Relation("org", target="orgs", display_field="name", cardinality=ONE)
        ),
        ManyToManyField(
            "teams", relation=Relation("teams", target="orgs", display_field="name", cardinality=MANY)
        ),
    ]


def test_relation_filter_matches_the_related_primary_key():
    admin = RowAdmin()
    kept = Row(1, org=Target(7, "Acme"))
    dropped = Row(2, org=Target(8, "Other"))
    unset = Row(3)
    objects = [kept, dropped, unset]

    assert RelationFilter("org").apply(objects, "7", admin) == [kept]
    # An unset relation never matches a chosen pk.
    assert RelationFilter("org").apply(objects, "0", admin) == []


def test_relation_filter_matches_any_member_of_a_many_relation():
    admin = RowAdmin()
    platform, security = Target(9, "Platform"), Target(10, "Security")
    kept = Row(1, teams=[security, platform])
    dropped = Row(2, teams=[security])

    assert RelationFilter("teams").apply([kept, dropped], "9", admin) == [kept]


def test_relation_filter_honours_a_custom_pk_resolver():
    """apply gets the parent ModelAdmin, not the registry, so it cannot
    call the target's own get_pk. The default covers the common case and
    related_pk is the escape hatch."""
    admin = RowAdmin()
    kept = Row(1, org=Target(7, "Acme"))
    dropped = Row(2, org=Target(8, "Other"))

    filt = RelationFilter("org", related_pk=lambda related: related.name)
    assert filt.apply([kept, dropped], "Acme", admin) == [kept]


def test_relation_filter_leaves_its_choices_to_the_adapter():
    assert RelationFilter("org").choices_with_labels() == [("", "All")]
    assert RelationFilter("org").control_kind == FILTER_KIND_RELATION


def test_relation_filter_with_no_value_narrows_nothing():
    admin = RowAdmin()
    objects = [Row(1, org=Target(7, "Acme")), Row(2)]
    assert RelationFilter("org").apply(objects, "", admin) == objects
