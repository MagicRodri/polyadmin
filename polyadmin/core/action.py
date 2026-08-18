"""Action: a ModelAdmin capability applied to one or more records.

An Action is invoked with a list of objects either way -- a "record"
action from the detail page passes a list of exactly one, a "bulk"
action from the list view's row-selection passes as many as were
checked. There's deliberately no separate record/bulk class: the same
Action definition serves both, since the handler never needs to know
which UI entry point it was invoked from.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence

ActionHandler = Callable[[Any, Sequence[Any], Any], "str | None"]


class Action:
    def __init__(
        self,
        name: str,
        handler: ActionHandler,
        *,
        label: str | None = None,
        confirm: str | None = None,
        permission: str | None = None,
    ) -> None:
        self.name = name
        self.label = label or name.replace("_", " ").title()
        self.handler = handler
        # A confirmation prompt shown before running (the PinesUI modal
        # in components/action_confirm_modal.html) -- None means no
        # confirmation.
        self.confirm = confirm
        # Extra permission suffix checked via resource_permission(slug,
        # permission) alongside the resource's `.view` -- None means no
        # extra check beyond being able to see the resource at all.
        self.permission = permission
