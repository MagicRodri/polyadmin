"""Widget: a single dashboard tile.

Each widget type computes its own data via `get_data()` and names the
template that renders it (`template`), so an application can add a
custom widget type just by subclassing Widget and pointing `template`
at its own file -- no framework change required.

Every widget accepts either a static value or a `get_*` callable so
applications can wire in live data (a DB count, a cache lookup, ...)
without the widget caring where it came from.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence


class Widget:
    template = "admin/widgets/widget.html"

    def __init__(self, title: str, *, size: str = "md", permission: str | None = None) -> None:
        self.title = title
        self.size = size
        self.permission = permission

    def get_data(self) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement get_data().")


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
    """A headline number paired with its change against the previous
    period, e.g. "$45,385" and "12.5% up" -- adapted from Flowbite's
    admin-dashboard "Sales this week" card. Metric answers "what is it
    now?"; Stat also answers "which way is it moving?".

    `delta` is the signed percentage change, so -4.2 means "down
    4.2%". The widget assumes up is good (green) and down is bad
    (red); for a metric where that's inverted, such as an error rate,
    negate the delta and say so in the title.
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
        # The template branches on `direction` rather than on the sign
        # of `delta`, which keeps the arrow and color choice out of the
        # markup. `delta` itself is reported unsigned, since the arrow
        # already carries the direction.
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


# Distinct qualitative palette for Donut slices, spaced around the
# color wheel (blue/violet/teal/amber/rose/cyan @ 500) so up to 6
# categories stay visually distinguishable at a glance -- deliberately
# skips green/orange/red, which components/toasts.html already uses
# for success/warning/danger, so a slice is never mistaken for a
# status color.
_DONUT_COLORS = ("blue-500", "violet-500", "teal-500", "amber-500", "rose-500", "cyan-500")


class Donut(Widget):
    """A share-of-total breakdown, e.g. "Traffic by device" (Desktop /
    Phone / Tablet), rendered as an SVG ring with a legend -- adapted
    from Flowbite's admin-dashboard "Traffic by device" card. Built
    from a handful of SVG <circle> arcs (stroke-dasharray), the same
    "no charting-library dependency" stance as Chart."""

    template = "admin/widgets/donut.html"

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
                    # The classic SVG-ring trick: a circle with
                    # circumference 100 (r=15.9155) lets stroke-dasharray
                    # use percentages directly. 25 rotates the first
                    # slice's start point to 12 o'clock; each following
                    # slice is pushed further by its predecessors'
                    # combined share.
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
    """A vertical feed of dated events, drawn as a rail of dots --
    adapted from Flowbite's admin-dashboard "Latest Activity" card.
    Activity's flat strings are enough for a short "who did what"
    list; Timeline is for entries that each need a timestamp and a
    body of their own.

    Entries are `(time, title, description)` triples. `time` is
    already formatted for display ("April 2023", "2h ago") -- the
    widget never parses or localizes it, so an application keeps full
    control of how its timestamps read. `description` may be empty.
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
    """Several widgets stacked into one card, one visible at a time --
    adapted from Flowbite's admin-dashboard "Statistics this month"
    card, which swaps a "Top products" table for a "Top customers"
    one.

    Panels are `(label, widget)` pairs. Tabs holds no data of its own;
    every panel's widget still computes its own, and all of them are
    computed on render (not on first click), so a panel backed by a
    slow query costs the same whether or not anyone opens it.
    """

    template = "admin/widgets/tabs.html"

    def __init__(
        self, title: str, *, panels: Sequence[tuple[str, Widget]] = (), **kwargs: Any
    ) -> None:
        super().__init__(title, **kwargs)
        self.panels = list(panels)

    def get_data(self) -> dict[str, Any]:
        # The widgets themselves are handed to the template, which
        # renders each through the same `{% include widget.template %}`
        # the dashboard uses for a top-level widget.
        return {"panels": [{"label": label, "widget": widget} for label, widget in self.panels]}
