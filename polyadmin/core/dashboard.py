"""Dashboard: a separate first-class concept.

The dashboard route is `GET /admin`. It's independent of any single
ModelAdmin -- a Dashboard is just a collection of Widgets, each
deciding its own data and, optionally, its own extra permission. Filters
narrow what context-aware widgets show, and exports hand the current
filters to a host function that returns a file (docs/dashboard.md).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from polyadmin.core._async import maybe_await
from polyadmin.core.widget import Widget


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class DashboardContext:
    filters: dict[str, Any]
    principal: Any = None


@dataclass(frozen=True)
class WidgetContext(DashboardContext):
    search: str | None = None
    offset: int = 0
    limit: int | None = None


def _parse_date(raw: str | None, default: date) -> date:
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


class DashboardFilter:
    """A dashboard-wide control. It parses its own query parameters into a
    typed value and never raises on user input: anything it cannot read
    falls back to its default."""

    kind = ""

    def __init__(self, name: str, *, label: str | None = None) -> None:
        self.name = name
        self.label = label or name.replace("_", " ").title()

    def parse(self, query: Mapping[str, str]) -> Any:
        raise NotImplementedError

    def query_params(self, value: Any) -> dict[str, str]:
        raise NotImplementedError


class DateRangeFilter(DashboardFilter):
    kind = "date_range"

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        default_days: int = 30,
        today: Callable[[], date] = date.today,
    ) -> None:
        super().__init__(name, label=label)
        self.default_days = default_days
        self._today = today

    @property
    def from_param(self) -> str:
        return f"{self.name}_from"

    @property
    def to_param(self) -> str:
        return f"{self.name}_to"

    def default(self) -> DateRange:
        end = self._today()
        return DateRange(end - timedelta(days=self.default_days), end)

    def parse(self, query: Mapping[str, str]) -> DateRange:
        fallback = self.default()
        start = _parse_date(query.get(self.from_param), fallback.start)
        end = _parse_date(query.get(self.to_param), fallback.end)
        if start > end:
            start, end = end, start
        return DateRange(start, end)

    def query_params(self, value: DateRange) -> dict[str, str]:
        return {self.from_param: value.start.isoformat(), self.to_param: value.end.isoformat()}


class SelectFilter(DashboardFilter):
    kind = "select"

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        empty_label: str | None = None,
        choices: Sequence[tuple[Any, Any]] = (),
        get_choices: Callable[[], Any] | None = None,
        searchable: bool = False,
    ) -> None:
        super().__init__(name, label=label)
        self.empty_label = empty_label
        # A search box in the open list, for a long list of choices.
        self.searchable = searchable
        self.choices = list(choices)
        self._get_choices = get_choices

    def parse(self, query: Mapping[str, str]) -> str | None:
        return query.get(self.name) or None

    def query_params(self, value: str | None) -> dict[str, str]:
        return {self.name: value} if value else {}

    async def resolve_choices(self) -> list[tuple[str, str]]:
        """Only called to render the page: a fragment request trusts the
        posted value rather than loading every choice to check it."""
        choices = self.choices if self._get_choices is None else await maybe_await(self._get_choices())
        return [(str(value), str(label)) for value, label in choices]


@dataclass(frozen=True)
class DashboardExport:
    """A button on the filter bar. `handler(ctx: DashboardContext)` returns a
    `Download` built from the current filters."""

    name: str
    label: str
    handler: Callable[[DashboardContext], Any]
    permission: str = "dashboard.export"


def _require_unique(values: Sequence[str], what: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Dashboard has more than one {what} {value!r}.")
        seen.add(value)


class Dashboard:
    def __init__(
        self,
        *,
        title: str = "Dashboard",
        widgets: Sequence[Widget] = (),
        filters: Sequence[DashboardFilter] = (),
        exports: Sequence[DashboardExport] = (),
    ) -> None:
        self.title = title
        self.widgets = list(widgets)
        self.filters = list(filters)
        self.exports = list(exports)

    def get_widgets(
        self, principal: Any = None, authorizer: Any = None
    ) -> list[Widget]:
        """Widgets visible to `principal`: a widget with no
        `permission` is always shown; one that names a permission is
        simply omitted -- not shown-disabled -- if the authorizer
        denies it (or there's no authorizer to ask, in which case it's
        shown, matching the rest of the framework's no-authorizer
        default of permitting everything).
        """
        visible = []
        for widget in self.widgets:
            if (
                widget.permission is None
                or authorizer is None
                or authorizer.can(principal, widget.permission, widget)
            ):
                visible.append(widget)
        return visible

    def get_exports(self, principal: Any = None, authorizer: Any = None) -> list[DashboardExport]:
        return [e for e in self.exports if authorizer is None or authorizer.can(principal, e.permission, e)]

    def get_widget(self, key: str) -> Widget | None:
        return next((w for w in self.widgets if w.key == key), None)

    def validate(self) -> None:
        names = [f.name for f in self.filters]
        _require_unique(names, "filter name")
        _require_unique([w.key for w in self.widgets], "widget key")
        _require_unique([e.name for e in self.exports], "export name")
        for widget in self.widgets:
            for name in widget.depends_on or ():
                if name not in names:
                    raise ValueError(f"Dashboard widget {widget.key!r} depends on unknown filter {name!r}.")

    def parse_filters(self, query: Mapping[str, str]) -> dict[str, Any]:
        return {f.name: f.parse(query) for f in self.filters}

    def query_params(self, filters: Mapping[str, Any]) -> dict[str, str]:
        params: dict[str, str] = {}
        for f in self.filters:
            params.update(f.query_params(filters[f.name]))
        return params

    def context(self, query: Mapping[str, str], principal: Any = None) -> DashboardContext:
        return DashboardContext(self.parse_filters(query), principal)

    def widget_context(self, widget: Widget, query: Mapping[str, str], principal: Any = None) -> WidgetContext:
        try:
            offset = max(int(query.get("offset") or 0), 0)
        except ValueError:
            offset = 0
        return WidgetContext(
            self.parse_filters(query),
            principal,
            search=query.get("search") or None,
            offset=offset,
            limit=getattr(widget, "page_size", None),
        )
