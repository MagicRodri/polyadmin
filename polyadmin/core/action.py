"""Actions: ModelAdmin methods applied to one or more records.

An action is invoked with a list of objects either way -- a "record" action
from the detail page passes a list of exactly one, a "bulk" action from the
list view's row-selection passes as many as were checked. There is
deliberately no separate record/bulk type: the same method serves both,
since it never needs to know which UI entry point invoked it.

Declare one by decorating a ModelAdmin method with `@action`. The decorator
only records options on the function; ModelAdmin.get_actions() resolves them
(see `collect_actions`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, overload

from polyadmin.core.auth import Principal

# Which pages offer an action: the list page's bulk bar, one record's detail
# page, or both.
ActionWhere = Literal["list", "detail", "both"]
ACTION_WHERE: tuple[str, ...] = ("list", "detail", "both")

# The bound method a ModelAdmin's action resolves to. It may be a coroutine
# function; the adapter awaits it when it is one.
ActionHandler = Callable[[Sequence[Any], Principal | None], Awaitable[str | None] | str | None]

# The built-in bulk delete's action name. Reserved: overriding the
# ModelAdmin.delete_selected method replaces the built-in, which is how you
# customise the confirmation text or the deletion itself.
DELETE_SELECTED_NAME = "delete_selected"

F = TypeVar("F", bound=Callable[..., Any])

_OPTIONS_ATTR = "__polyadmin_action__"


@dataclass(frozen=True)
class ActionOptions:
    """What `@action` records on a method."""

    label: str | None = None
    # A confirmation prompt shown before running (the dialog in
    # components/action_confirm_modal.html) -- None means no confirmation.
    confirm: str | None = None
    # Extra permission suffix checked via resource_permission(slug,
    # permission) alongside the resource's `.view` -- None means no extra
    # check beyond being able to see the resource at all.
    permission: str | None = None
    # Placement only, not authorization: the action route serves every action
    # whichever page offered it, and checks `permission` there.
    where: ActionWhere = "both"


@dataclass(frozen=True)
class Action:
    """One resolved action of one ModelAdmin instance. Built by
    `collect_actions`; not something a host constructs."""

    name: str
    handler: ActionHandler
    label: str
    confirm: str | None = None
    permission: str | None = None
    where: ActionWhere = "both"


@overload
def action(func: F, /) -> F: ...


@overload
def action(
    *,
    label: str | None = None,
    confirm: str | None = None,
    permission: str | None = None,
    where: ActionWhere = "both",
) -> Callable[[F], F]: ...


def action(
    func: F | None = None,
    /,
    *,
    label: str | None = None,
    confirm: str | None = None,
    permission: str | None = None,
    where: ActionWhere = "both",
) -> F | Callable[[F], F]:
    """Mark a ModelAdmin method as an action: `(self, objects, principal) -> str | None`.

    The method's name is the action's name. The decorator returns the function
    unchanged, so type checkers keep seeing its own signature.
    """
    if where not in ACTION_WHERE:
        raise ValueError(f"@action: where must be one of {ACTION_WHERE}, not {where!r}.")
    options = ActionOptions(label=label, confirm=confirm, permission=permission, where=where)

    def decorate(fn: F) -> F:
        setattr(fn, _OPTIONS_ATTR, options)
        return fn

    return decorate(func) if func is not None else decorate


def collect_actions(model_admin: Any) -> list[Action]:
    """The actions `model_admin` declares, in definition order.

    The class hierarchy is walked base-first, so a subclass's actions follow
    its base's. A subclass that re-decorates a name replaces that name's
    options but keeps its position; one that overrides the method without
    decorating it keeps the base's options and runs its own body, because the
    handler is looked up on the instance.
    """
    found: dict[str, ActionOptions] = {}
    for klass in reversed(type(model_admin).__mro__):
        for name, member in vars(klass).items():
            options = getattr(member, _OPTIONS_ATTR, None)
            if isinstance(options, ActionOptions):
                found[name] = options
    return [
        Action(
            name=name,
            handler=getattr(model_admin, name),
            label=options.label or name.replace("_", " ").title(),
            confirm=options.confirm,
            permission=options.permission,
            where=options.where,
        )
        for name, options in found.items()
    ]
