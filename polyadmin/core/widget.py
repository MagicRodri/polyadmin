"""Widget: a single dashboard tile.

Each type computes its own data via `get_data()` and names the template that
renders it, so a custom widget is a subclass pointing `template` at its own
file -- no framework change required. Every widget takes either a static value
or a `get_*` callable, so an application can wire in live data without the
widget caring where it came from.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from polyadmin.core._async import maybe_await
from polyadmin.core.slug import slugify
from polyadmin.i18n import gettext


class WidgetUnavailable(Exception):
    """Raised by a widget's data function to show its unavailable state with
    `message`, e.g. when the service behind it is down."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def takes_context(fn: Callable[..., Any]) -> bool:
    """Whether `fn` accepts a positional argument, i.e. wants the context."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    return any(p.kind in kinds for p in parameters)


def _is_context_aware(fn: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(fn) or takes_context(fn)


def call_with_context(fn: Callable[..., Any], ctx: Any) -> Any:
    return fn(ctx) if takes_context(fn) else fn()


async def resolve_widget_data(widget: Widget, ctx: Any) -> Any:
    return await maybe_await(call_with_context(widget.get_data, ctx))


WIDGET_PLACEMENTS = ("grid", "top")


class Widget:
    template = "admin/widgets/widget.html"

    def __init__(
        self,
        title: str,
        *,
        size: str = "md",
        permission: str | None = None,
        key: str | None = None,
        depends_on: Sequence[str] | None = None,
        description: str | Callable[[Any], str] | None = None,
        empty_text: str | None = None,
        placement: str = "grid",
    ) -> None:
        if placement not in WIDGET_PLACEMENTS:
            raise ValueError(f"Widget {title!r}: placement must be one of {WIDGET_PLACEMENTS}, not {placement!r}.")
        self.title = title
        self.size = size
        self.permission = permission
        self.key = key or slugify(title)
        # None reloads on every filter; an empty list on none.
        self.depends_on = None if depends_on is None else list(depends_on)
        self.description = description
        self.empty_text = empty_text
        # "top" renders above the filter bar, full width and without the
        # card's header -- a summary row rather than one more card.
        self.placement = placement

    def get_data(self) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement get_data().")

    def describe(self, ctx: Any) -> str | None:
        return self.description(ctx) if callable(self.description) else self.description

    def reloads_on(self, filter_names: Sequence[str]) -> list[str]:
        if self.depends_on is None:
            return list(filter_names)
        return [name for name in self.depends_on if name in filter_names]

    @property
    def lazy(self) -> bool:
        """Loaded from its fragment route rather than rendered with the page:
        its data needs the request's context or has to be awaited."""
        return inspect.iscoroutinefunction(self.get_data) or takes_context(self.get_data)


class Metric(Widget):
    """A single headline number, e.g. "1,204 users"."""

    template = "admin/widgets/metric.html"

    def __init__(
        self, title: str, *, value: Any = None, get_value: Callable[[], Any] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(title, **kwargs)
        self._value = value
        self._get_value = get_value

    def get_data(self) -> dict[str, Any]:
        value = self._get_value() if self._get_value is not None else self._value
        return {"value": value}


class Stat(Widget):
    """A headline number paired with its change against the previous period.
    Metric answers "what is it now?"; Stat also answers "which way is it
    moving?".

    `delta` is the signed percentage change. Up is assumed good; for an
    inverted metric such as an error rate, negate the delta and say so in the
    title.
    """

    template = "admin/widgets/stat.html"

    def __init__(
        self,
        title: str,
        *,
        value: Any = None,
        delta: float = 0.0,
        get_stat: Callable[[], tuple[Any, float]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._value = value
        self._delta = delta
        self._get_stat = get_stat

    def get_data(self) -> dict[str, Any]:
        value, delta = (
            self._get_stat() if self._get_stat is not None else (self._value, self._delta)
        )
        # The template branches on `direction`, not the sign of `delta`,
        # keeping the arrow and colour choice out of the markup. `delta`
        # is reported unsigned, since the arrow carries the direction.
        direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
        return {"value": value, "delta": round(abs(delta), 1), "direction": direction}


class Progress(Widget):
    """A value against a target, e.g. "42 / 100 tasks complete"."""

    template = "admin/widgets/progress.html"

    def __init__(
        self,
        title: str,
        *,
        value: float = 0,
        target: float = 100,
        get_data: Callable[[], tuple[float, float]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._value = value
        self._target = target
        self._get_data = get_data

    def get_data(self) -> dict[str, Any]:
        value, target = self._get_data() if self._get_data is not None else (self._value, self._target)
        percent = 0 if target <= 0 else min(100, round(value / target * 100))
        return {"value": value, "target": target, "percent": percent}


class Table(Widget):
    """Small tabular data: columns + rows (each row a dict keyed by column)."""

    template = "admin/widgets/table.html"

    def __init__(
        self,
        title: str,
        *,
        columns: Sequence[str] = (),
        rows: Sequence[dict[str, Any]] = (),
        get_rows: Callable[[], Sequence[dict[str, Any]]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self.columns = list(columns)
        self._rows = list(rows)
        self._get_rows = get_rows

    def get_data(self) -> dict[str, Any]:
        rows = self._get_rows() if self._get_rows is not None else self._rows
        return {"columns": self.columns, "rows": list(rows)}


class Chart(Widget):
    """Labeled values rendered as simple CSS bars -- no charting-library
    dependency, since the framework ships with none."""

    template = "admin/widgets/chart.html"

    def __init__(
        self,
        title: str,
        *,
        series: Sequence[tuple[str, float]] = (),
        get_series: Callable[[], Sequence[tuple[str, float]]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._series = list(series)
        self._get_series = get_series

    def get_data(self) -> dict[str, Any]:
        series = list(self._get_series() if self._get_series is not None else self._series)
        maximum = max((value for _, value in series), default=0) or 1
        return {"series": [(label, value, round(value / maximum * 100)) for label, value in series]}


# The qualitative palette for Donut slices, spaced around the wheel so six
# categories stay distinguishable. They name theme.html's --chart-*
# variables rather than literal shades, so a Donut follows the active
# theme and is re-tuned for dark mode. No slice lands on the
# success/warning/danger hues, so it cannot be mistaken for a status.
_DONUT_COLORS = ("chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-6")


class Donut(Widget):
    """A share-of-total breakdown drawn as an SVG ring with a legend, built from
    <circle> arcs -- the same no-charting-library stance as Chart.
    """

    template = "admin/widgets/donut.html"

    def __init__(
        self,
        title: str,
        *,
        series: Sequence[tuple[str, float]] = (),
        get_series: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._series = list(series)
        self._get_series = get_series

    @property
    def lazy(self) -> bool:
        return self._get_series is not None and _is_context_aware(self._get_series)

    def get_data(self, ctx: Any = None) -> Any:
        """The ring's slices. A `get_series` that takes the context or is async
        makes the donut load from its fragment route; the result is then a
        coroutine the adapter awaits."""
        if self._get_series is None:
            return self._shape(list(self._series))
        series = call_with_context(self._get_series, ctx)
        if inspect.isawaitable(series):
            return self._ashape(series)
        return self._shape(list(series))

    async def _ashape(self, series: Any) -> dict[str, Any]:
        return self._shape(list(await series))

    @staticmethod
    def _shape(series: list[tuple[str, float]]) -> dict[str, Any]:
        total = sum(value for _, value in series)
        slices = []
        cumulative = 0.0
        for i, (label, value) in enumerate(series):
            percent = 0.0 if total <= 0 else value / total * 100
            slices.append(
                {
                    "label": label,
                    "value": value,
                    "percent": round(percent, 1),
                    # A circle of circumference 100 (r=15.9155) lets
                    # stroke-dasharray take percentages directly. 25
                    # rotates the first slice to 12 o'clock; each later
                    # one is pushed by its predecessors' combined share.
                    "dash_offset": round(25 - cumulative, 4),
                    "color": _DONUT_COLORS[i % len(_DONUT_COLORS)],
                }
            )
            cumulative += percent
        return {"slices": slices, "total": total}


class Activity(Widget):
    """A recent-activity feed: a list of short text entries."""

    template = "admin/widgets/activity.html"

    def __init__(
        self,
        title: str,
        *,
        entries: Sequence[str] = (),
        get_entries: Callable[[], Sequence[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._entries = list(entries)
        self._get_entries = get_entries

    def get_data(self) -> dict[str, Any]:
        entries = self._get_entries() if self._get_entries is not None else self._entries
        return {"entries": list(entries)}


class Timeline(Widget):
    """A vertical feed of dated events drawn as a rail of dots. Activity's flat
    strings suit a short "who did what" list; Timeline is for entries needing a
    timestamp and a body of their own.

    Entries are `(time, title, description)` triples. `time` arrives already
    formatted: the widget never parses or localizes it, so the application
    controls how its timestamps read.
    """

    template = "admin/widgets/timeline.html"

    def __init__(
        self,
        title: str,
        *,
        entries: Sequence[tuple[str, str, str]] = (),
        get_entries: Callable[[], Sequence[tuple[str, str, str]]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self._entries = list(entries)
        self._get_entries = get_entries

    def get_data(self) -> dict[str, Any]:
        entries = self._get_entries() if self._get_entries is not None else self._entries
        return {
            "entries": [
                {"time": time, "title": title, "description": description}
                for time, title, description in entries
            ]
        }


class Tabs(Widget):
    """Several widgets stacked into one card, one visible at a time.

    Panels are `(label, widget)` pairs. Tabs holds no data itself, and every
    panel is computed on render rather than on first click, so a panel backed
    by a slow query costs the same whether or not anyone opens it.
    """

    template = "admin/widgets/tabs.html"

    def __init__(
        self, title: str, *, panels: Sequence[tuple[str, Widget]] = (), **kwargs: Any
    ) -> None:
        super().__init__(title, **kwargs)
        self.panels = list(panels)

    @property
    def lazy(self) -> bool:
        """Loaded from its fragment route when any panel is."""
        return any(widget.lazy for _, widget in self.panels)

    def get_data(self, ctx: Any = None) -> Any:
        # Handed to the template, which renders each panel's data through the
        # same `{% include widget.template %}` the dashboard uses.
        if self.lazy:
            return self._aget_data(ctx)
        return {"panels": [{"label": label, "widget": widget, "data": widget.get_data()} for label, widget in self.panels]}

    async def _aget_data(self, ctx: Any) -> dict[str, Any]:
        return {
            "panels": [
                {"label": label, "widget": widget, "data": await resolve_widget_data(widget, ctx)}
                for label, widget in self.panels
            ]
        }


@dataclass(frozen=True)
class Tile:
    label: str
    value: Any
    icon: str | None = None
    hint: str | None = None


class MetricGroup(Widget):
    """A row of headline numbers produced by one data call -- one request to
    a service that answers all of them, where separate Metrics would make
    one each."""

    template = "admin/widgets/metric_group.html"

    def __init__(self, title: str, *, get_tiles: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(title, **kwargs)
        self._get_tiles = get_tiles

    async def get_data(self, ctx: Any) -> dict[str, Any]:
        tiles = list(await maybe_await(call_with_context(self._get_tiles, ctx)))
        return {"tiles": tiles, "empty": not tiles}


COLUMN_FORMATS = ("text", "number", "datetime", "share", "percent")
TONE_VARIANTS = ("success", "warning", "danger")


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    align: str = "start"
    format: str = "text"
    strong: bool = False
    empty: str | None = None
    # (minimum, colour) pairs: a numeric value renders as a badge in the
    # colour of the highest minimum it reaches, e.g. ((80, "success"),
    # (50, "warning"), (0, "danger")) for a success rate.
    tones: tuple[tuple[float, str], ...] = ()

    def __post_init__(self) -> None:
        for _, tone in self.tones:
            if tone not in TONE_VARIANTS:
                raise ValueError(f"Column {self.key!r}: tone must be one of {TONE_VARIANTS}, not {tone!r}.")
        if self.format not in COLUMN_FORMATS:
            raise ValueError(f"Column {self.key!r}: format must be one of {COLUMN_FORMATS}, not {self.format!r}.")
        if self.align not in ("start", "end"):
            raise ValueError(f"Column {self.key!r}: align must be 'start' or 'end', not {self.align!r}.")


@dataclass(frozen=True)
class Rows:
    """One page of a DataTable. `total` is the size of the whole result when
    known; `totals` is a summary row shown above the first page."""

    items: list[dict[str, Any]]
    total: int | None = None
    totals: dict[str, Any] | None = None


def next_offset(rows: Rows, offset: int, limit: int | None) -> int | None:
    """Where the next page starts, or None when this was the last one. With
    no total, a page shorter than the limit is the last."""
    if limit is None or not rows.items:
        return None
    shown = offset + len(rows.items)
    if rows.total is not None:
        return shown if shown < rows.total else None
    return shown if len(rows.items) == limit else None


class DataTable(Widget):
    """Rows the host fetches page by page, e.g. from another service.
    Scrolling to the last row loads the next page."""

    template = "admin/widgets/data_table.html"

    def __init__(
        self,
        title: str,
        *,
        columns: Sequence[Column],
        get_rows: Callable[..., Any],
        page_size: int | None = 50,
        searchable: bool = False,
        search_placeholder: str | None = None,
        total_label: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(title, **kwargs)
        self.columns = list(columns)
        self._get_rows = get_rows
        self.page_size = page_size
        self.searchable = searchable
        self.search_placeholder = search_placeholder
        self.total_label = total_label

    async def get_data(self, ctx: Any) -> dict[str, Any]:
        rows = await maybe_await(call_with_context(self._get_rows, ctx))
        if not isinstance(rows, Rows):
            raise TypeError(f"DataTable {self.key!r}: get_rows must return Rows, not {type(rows).__name__}.")
        footer = None
        if self.total_label and rows.total is not None:
            footer = gettext(self.total_label).replace("{total}", str(rows.total))
        return {
            "columns": self.columns,
            "rows": rows,
            "next_offset": next_offset(rows, ctx.offset, ctx.limit),
            "empty": ctx.offset == 0 and not rows.items and not rows.totals,
            "footer": footer,
        }
