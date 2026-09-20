"""Filter: a list-view constraint the user can toggle.

`filter.apply(objects, raw_value, model_admin)` is deliberately given
the raw, still-a-string query-param value -- parsing is the filter's
job, since only it knows what its own values mean.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

from polyadmin.core.relation import MANY
from polyadmin.i18n import N_


class Filter:
    # How this filter's control is sourced and drawn. It answers two
    # questions at once -- who supplies the choices, and what the panel
    # renders -- because they are the same decision: a filter that cannot
    # enumerate its own values is exactly the filter that needs a control
    # other than a list of links.
    #
    # "" is the default and is never declared: the filter supplies its own
    # choices and the panel draws links.
    control_kind: ClassVar[str] = ""

    def __init__(self, name: str, *, label: str | None = None):
        self.name = name
        self.label = label or name.replace("_", " ").title()

    def choices_with_labels(self) -> list[tuple[str, str]]:
        """(value, label) pairs for a <select>, "" always meaning "no filter"."""
        raise NotImplementedError

    def apply(self, objects: list[Any], raw_value: str, model_admin: Any) -> list[Any]:
        raise NotImplementedError


class BooleanFilter(Filter):
    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [("", N_("All")), ("true", N_("Yes")), ("false", N_("No"))]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field(self.name)
        want = raw_value.lower() in ("true", "1", "on", "yes")
        return [obj for obj in objects if bool(field.get_value(obj)) == want]


class ChoiceFilter(Filter):
    def __init__(self, name: str, *, choices: Sequence[Any], label: str | None = None):
        super().__init__(name, label=label)
        self.choices = list(choices)

    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [("", N_("All"))] + [(str(choice), str(choice)) for choice in self.choices]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field(self.name)
        return [obj for obj in objects if str(field.get_value(obj)) == raw_value]


# The adapter supplies the choices, from the target ModelAdmin --
# choices_with_labels cannot, because it reaches neither the registry nor
# the principal.
FILTER_KIND_RELATION = "relation"
# The filter's own choices are presets, and the panel adds two date inputs
# below them.
FILTER_KIND_DATE_RANGE = "daterange"

# The empty filter's values. Stable strings, because they end up in URLs.
EMPTY_FILTER_EMPTY = "empty"
EMPTY_FILTER_NOT_EMPTY = "notempty"


def is_empty_value(value: Any) -> bool:
    """Whether a field's value counts as empty: unset or blank, never
    merely zero. None, "", an empty collection and a zero datetime are
    empty; 0, False and "0" are values somebody chose, and are not.
    """
    if value is None:
        return True
    # Before the length checks below, because False is not empty and bool
    # is a subclass of int.
    if isinstance(value, bool | int | float):
        return False
    # datetime.min/date.min are sentinels here, not moments in time: Go's
    # zero time.Time is how that side represents an unset date, and the
    # two implementations agree on what empty means. DTZ901 is about
    # building naive datetimes for logic; an equality test against the
    # sentinel is exactly what is meant, and comparing an aware value
    # against a naive one returns False rather than raising.
    if isinstance(value, datetime):
        return value == datetime.min  # noqa: DTZ901
    if isinstance(value, date):
        return value == date.min
    if isinstance(value, str | list | tuple | set | dict):
        return len(value) == 0
    return False


class EmptyFilter(Filter):
    """Splits a list on whether a field has a value at all. It applies to
    relation fields too -- "organization is empty" is the case that earns
    it -- where a `many` relation is empty when it has no members.
    """

    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [
            ("", N_("All")),
            (EMPTY_FILTER_EMPTY, N_("Empty")),
            (EMPTY_FILTER_NOT_EMPTY, N_("Not empty")),
        ]

    def apply(self, objects, raw_value, model_admin):
        if raw_value == EMPTY_FILTER_EMPTY:
            want_empty = True
        elif raw_value == EMPTY_FILTER_NOT_EMPTY:
            want_empty = False
        else:
            # "" and anything crafted narrow nothing.
            return objects
        try:
            field = model_admin.get_field(self.name)
        except KeyError:
            return objects
        return [obj for obj in objects if is_empty_value(field.get_value(obj)) is want_empty]


# The date filter's values. Stable strings, because they end up in URLs.
DATE_FILTER_TODAY = "today"
DATE_FILTER_PAST_7_DAYS = "7d"
DATE_FILTER_THIS_MONTH = "month"
DATE_FILTER_THIS_YEAR = "year"

# The date format a custom range uses, in the URL and in the panel's two
# inputs. It is what <input type="date"> posts, so the form needs no
# reformatting.
DATE_FILTER_RANGE_FORMAT = "%Y-%m-%d"


def date_filter_range(raw_value: str, now: datetime) -> tuple[date, date] | None:
    """The half-open window [from, to) a value means, relative to now. None
    for "" and for anything unrecognised, so a crafted URL narrows nothing
    rather than failing."""
    day = now.date()
    if raw_value == DATE_FILTER_TODAY:
        return day, day + timedelta(days=1)
    if raw_value == DATE_FILTER_PAST_7_DAYS:
        # Inclusive of today, so "past 7 days" counts seven days, not eight.
        return day - timedelta(days=6), day + timedelta(days=1)
    if raw_value == DATE_FILTER_THIS_MONTH:
        start = day.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1)
    if raw_value == DATE_FILTER_THIS_YEAR:
        return day.replace(month=1, day=1), day.replace(year=day.year + 1, month=1, day=1)

    # Not a preset, so try a custom range: "<from>:<to>", each YYYY-MM-DD.
    # It is inclusive of both endpoints, because that is what "from X to
    # Y" means to a reader, and is converted here to the same half-open
    # window the presets produce.
    start_text, separator, end_text = raw_value.partition(":")
    # An empty start is rejected: "through today" has a natural
    # resolution, "since the beginning of time" does not.
    if not separator or not start_text:
        return None
    try:
        start = datetime.strptime(start_text, DATE_FILTER_RANGE_FORMAT).date()  # noqa: DTZ007
        # An empty end means "through today", resolved here rather than in
        # the panel: the form posts the blank when scripting is off, and a
        # value the parser rejected would break the one path the panel's
        # links exist to protect.
        end = (
            datetime.strptime(end_text, DATE_FILTER_RANGE_FORMAT).date()  # noqa: DTZ007
            if end_text
            else day
        )
    except ValueError:
        return None
    if end < start:
        return None
    return start, end + timedelta(days=1)


def date_filter_range_values(raw_value: str) -> tuple[str, str] | None:
    """The two strings a custom range carries, so the panel can prefill its
    inputs. Parses nothing: None for a preset and for anything without a
    separator.
    """
    start_text, separator, end_text = raw_value.partition(":")
    if not separator or not start_text:
        return None
    return start_text, end_text


class DateFilter(Filter):
    """Narrows a list to a window around today: the presets a reader actually
    asks for ("what came in this week?"), rather than two date boxes to fill
    in. Declared like any other filter -- filters = [DateFilter("founded")] --
    and so it renders in the same filter panel and rides in the same
    ListRequest, which means exports and delete_selected narrow with it.

    A `list_page` implementation reads the raw value and resolves it in its
    own query; `date_filter_range` turns a value into the same window this
    applies in memory, so the two cannot drift.
    """

    # Its own choices are the presets; the panel draws two date inputs
    # below them.
    control_kind: ClassVar[str] = FILTER_KIND_DATE_RANGE

    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [
            ("", N_("Any date")),
            (DATE_FILTER_TODAY, N_("Today")),
            (DATE_FILTER_PAST_7_DAYS, N_("Past 7 days")),
            (DATE_FILTER_THIS_MONTH, N_("This month")),
            (DATE_FILTER_THIS_YEAR, N_("This year")),
        ]

    def apply(self, objects, raw_value, model_admin):
        window = date_filter_range(raw_value, datetime.now())  # noqa: DTZ005 -- the reader's own day
        if window is None:
            return objects
        start, end = window
        try:
            field = model_admin.get_field(self.name)
        except KeyError:
            return objects
        kept = []
        for obj in objects:
            value = field.get_value(obj)
            # Compared as a date: a datetime's clock time must not decide
            # whether it falls in "today".
            if isinstance(value, datetime):
                value = value.date()
            if isinstance(value, date) and start <= value < end:
                kept.append(obj)
        return kept


class RelationFilter(Filter):
    """Narrows a list to rows pointing at one related record. The URL
    carries the target's primary key, so a filtered list is a link like
    any other.

    Its choices come from the adapter, not from here: choices_with_labels
    reaches neither the registry nor the principal, and a filter must not
    offer records from a target the reader may not view.
    """

    control_kind: ClassVar[str] = FILTER_KIND_RELATION

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        related_pk: Callable[[Any], Any] | None = None,
    ):
        super().__init__(name, label=label)
        # Resolves the related object's primary key. Defaults to the lookup
        # ModelAdmin.get_pk uses. Set it when the target declares its own:
        # apply receives the parent ModelAdmin, not the registry, and
        # Relation.target is a slug, so core cannot call the target's
        # get_pk for you.
        self.related_pk = related_pk

    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [("", N_("All"))]

    def _pk(self, related: Any) -> str:
        if related is None:
            return ""
        pk = self.related_pk(related) if self.related_pk else getattr(related, "id", None)
        return "" if pk is None else str(pk)

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        try:
            field = model_admin.get_field(self.name)
        except KeyError:
            return objects
        relation = getattr(field, "relation", None)
        if relation is None:
            return objects
        many = relation.cardinality == MANY
        kept = []
        for obj in objects:
            related = relation.get_value(obj)
            if related is None:
                continue
            if not many:
                if self._pk(related) == raw_value:
                    kept.append(obj)
            # A `many` relation matches when any member does.
            elif any(self._pk(member) == raw_value for member in related):
                kept.append(obj)
        return kept
