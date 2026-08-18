"""AdminPage: an application-registered admin route with its own
template and handler, for functionality that isn't resource CRUD
(reports, wizards, internal tools) -- see docs/routing.md.

Named `AdminPage`, not `Page`, to avoid colliding with
`polyadmin.core.pagination.Page` (a paginated slice of list results).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

# String-quoted forward ref: PageContext lives in the FastAPI adapter
# (polyadmin.fastapi.pages), and core must not import adapter code.
# Handlers are async, matching every other FastAPI adapter handler in
# this framework (see fastapi/handlers.py's build_* functions).
PageHandler = Callable[["PageContext"], Awaitable[Any]]  # noqa: F821


class AdminPage:
    """A custom admin page: a path, an application-supplied handler,
    and the same sidebar-grouping/permission shape a ModelAdmin has.
    """

    def __init__(
        self,
        path: str,
        handler: PageHandler,
        *,
        label: str | None = None,
        category: str | None = None,
        icon: str = "collection",
        permission: str | None = None,
        methods: tuple[str, ...] = ("GET", "POST"),
        show_in_nav: bool = True,
    ) -> None:
        if not path.startswith("/"):
            raise ValueError(f"AdminPage path must start with '/': {path!r}")
        self.path = path
        self.handler = handler
        self.label = label or _default_label(path)
        self.category = category
        self.icon = icon
        self.permission = permission or _default_permission(path)
        self.methods = tuple(m.upper() for m in methods)
        self.show_in_nav = show_in_nav


def _default_label(path: str) -> str:
    last = path.strip("/").rsplit("/", 1)[-1] or "page"
    return last.replace("-", " ").replace("_", " ").title()


def _default_permission(path: str) -> str:
    # "/reports/contracts" -> "page.reports.contracts", the same
    # dotted shape as resource_permission's "{slug}.{action}".
    return "page." + path.strip("/").replace("/", ".")
