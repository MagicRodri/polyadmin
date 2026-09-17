"""Filter: a list-view constraint the user can toggle.

`filter.apply(objects, raw_value, model_admin)` is deliberately given
the raw, still-a-string query-param value -- parsing is the filter's
job, since only it knows what its own values mean.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from polyadmin.i18n import N_


class Filter:
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


# The date filter's values. Stable strings, because they end up in URLs.
DATE_FILTER_TODAY = "today"
DATE_FILTER_PAST_7_DAYS = "7d"
DATE_FILTER_THIS_MONTH = "month"
DATE_FILTER_THIS_YEAR = "year"


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
    return None


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
