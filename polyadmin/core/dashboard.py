"""Dashboard: a separate first-class concept.

The dashboard route is `GET /admin`. It's independent of any single
ModelAdmin -- a Dashboard is just a collection of Widgets, each
deciding its own data and, optionally, its own extra permission.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from polyadmin.core.widget import Widget


class Dashboard:
    def __init__(
        self, *, title: str = "Dashboard", widgets: Sequence[Widget] = ()
    ) -> None:
        self.title = title
        self.widgets = list(widgets)

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
