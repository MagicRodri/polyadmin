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

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from polyadmin.core.auth import Principal

if TYPE_CHECKING:
    from polyadmin.core.field import Field

# Which pages offer an action: the list page's bulk bar, one record's detail
# page, or both.
ActionWhere = Literal["list", "detail", "both"]
ACTION_WHERE: tuple[str, ...] = ("list", "detail", "both")

# The built-in bulk delete's action name. Reserved: overriding the
# ModelAdmin.delete_selected method replaces the built-in, which is how you
# customise the confirmation text or the deletion itself.
DELETE_SELECTED_NAME = "delete_selected"

BULK_EDIT_NAME = "bulk_edit"


@dataclass(frozen=True)
class Download:
    """A file an action answers with instead of a flash message."""

    filename: str
    content_type: str = "application/octet-stream"
    content: bytes | None = None
    stream: Iterator[bytes] | AsyncIterator[bytes] | None = None

    def __post_init__(self) -> None:
        if (self.content is None) == (self.stream is None):
            raise ValueError("Download needs exactly one of `content` or `stream`.")


class ActionError(RuntimeError):
    """Raised by an action to end it with an error or warning message instead
    of the success flash. A RuntimeError, so callers of the built-in bulk
    actions that caught RuntimeError still do."""

    def __init__(
        self,
        message: str,
        level: Literal["error", "warning"] = "error",
        done: Sequence[Any] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.level = level
        self.done = tuple(done)


class ActionFormError(Exception):
    """Raised by a form action's handler to redisplay the form with errors.
    The "" key holds messages that belong to no single field."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__(errors)
        self.errors = errors


# The bound method a ModelAdmin's action resolves to: (objects, principal),
# plus the validated `data` for a form action. It may be a coroutine
# function; the adapter awaits it when it is one.
ActionHandler = Callable[..., Awaitable[str | None | Download] | str | None | Download]

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
    # Fields asked for on a page of their own before the action runs, or a
    # callable building them from the ModelAdmin.
    form: Any = None
    submit_label: str | None = None


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
    form: tuple[Field, ...] | None = None
    submit_label: str | None = None


def _check_arity(fn: Callable[..., Any], *, has_form: bool) -> None:
    params = list(inspect.signature(fn).parameters.values())
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    required = sum(1 for p in positional if p.default is p.empty)
    if has_form and not (required <= 4 <= len(positional)):
        raise TypeError(f"@action {fn.__name__}: a form action takes (self, objects, principal, data).")
    if not has_form and required >= 4:
        raise TypeError(f"@action {fn.__name__}: takes `data` but declares no form.")


@overload
def action(func: F, /) -> F: ...


@overload
def action(
    *,
    label: str | None = None,
    confirm: str | None = None,
    permission: str | None = None,
    where: ActionWhere = "both",
    form: Any = None,
    submit_label: str | None = None,
) -> Callable[[F], F]: ...


def action(
    func: F | None = None,
    /,
    *,
    label: str | None = None,
    confirm: str | None = None,
    permission: str | None = None,
    where: ActionWhere = "both",
    form: Any = None,
    submit_label: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a ModelAdmin method as an action: `(self, objects, principal) -> str | None`,
    or `(self, objects, principal, data)` when it declares a `form`.

    The method's name is the action's name. The decorator returns the function
    unchanged, so type checkers keep seeing its own signature.
    """
    if where not in ACTION_WHERE:
        raise ValueError(f"@action: where must be one of {ACTION_WHERE}, not {where!r}.")
    if form is not None and confirm is not None:
        raise ValueError("@action: a form action cannot also take `confirm`; the form page is the confirmation.")
    options = ActionOptions(
        label=label, confirm=confirm, permission=permission, where=where, form=form, submit_label=submit_label
    )

    def decorate(fn: F) -> F:
        _check_arity(fn, has_form=form is not None)
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
            form=_resolve_form(options.form, model_admin),
            submit_label=options.submit_label,
        )
        for name, options in found.items()
    ]


def _resolve_form(form: Any, model_admin: Any) -> tuple[Field, ...] | None:
    if form is None:
        return None
    return tuple(form(model_admin) if callable(form) else form)
