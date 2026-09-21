"""Action: a ModelAdmin capability applied to one or more records.

An Action is invoked with a list of objects either way -- a "record"
action from the detail page passes a list of exactly one, a "bulk"
action from the list view's row-selection passes as many as were
checked. There's deliberately no separate record/bulk class: the same
Action definition serves both, since the handler never needs to know
which UI entry point it was invoked from.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from polyadmin.i18n import N_, gettext, ngettext

ActionHandler = Callable[[Any, Sequence[Any], Any], "str | None"]

# Which pages offer an action: the list page's bulk bar, one record's detail
# page, or both.
ACTION_WHERE = ("list", "detail", "both")


class Action:
    def __init__(
        self,
        name: str,
        handler: ActionHandler,
        *,
        label: str | None = None,
        confirm: str | None = None,
        permission: str | None = None,
        where: str = "both",
    ) -> None:
        if where not in ACTION_WHERE:
            raise ValueError(f"Action {name!r}: where must be one of {ACTION_WHERE}, not {where!r}.")
        self.name = name
        self.label = label or name.replace("_", " ").title()
        self.handler = handler
        # A confirmation prompt shown before running (the dialog in
        # components/action_confirm_modal.html) -- None means no
        # confirmation.
        self.confirm = confirm
        # Extra permission suffix checked via resource_permission(slug,
        # permission) alongside the resource's `.view` -- None means no
        # extra check beyond being able to see the resource at all.
        self.permission = permission
        # Placement only, not authorization: the action route serves every
        # action whichever page offered it, and checks `permission` there.
        self.where = where


# The built-in bulk delete's action name. Reserved: a ModelAdmin that
# declares an Action of the same name replaces the built-in rather than
# colliding with it, which is how you customise the confirmation text or
# the deletion itself.
DELETE_SELECTED_NAME = "delete_selected"


def delete_selected_action() -> Action:
    """The bulk delete every admin gets for free.

    Django ships the same one, and it is the single most common action
    anyone would otherwise write by hand.

    It is expressed entirely in terms of the ModelAdmin's own `delete`
    hook, so it works against whatever storage the application actually
    has and honours whatever that hook already does (cascades, soft
    deletes, hooks of its own).

    permission="delete", not the resource's bare "view": the action
    route checks it on top, so a principal who may look at a list but
    not destroy its rows is refused -- and, because the same check
    drives the listbox, never offered it in the first place.
    """

    def handler(model_admin, objects, principal):
        deleted = 0
        for obj in objects:
            try:
                model_admin.delete(obj)
            except Exception as exc:
                # Stop at the first failure and report how far it got:
                # silently continuing would leave the user unable to
                # tell which records survived.
                # Translators: a bulk delete stopped part-way. %(deleted)d of
                # %(total)d records were deleted; %(error)s is the underlying error.
                failure = gettext("Deleted %(deleted)d of %(total)d, then failed: %(error)s")
                raise RuntimeError(failure % {"deleted": deleted, "total": len(objects), "error": exc}) from exc
            deleted += 1
        return ngettext(
            "Deleted %(num)d record.", "Deleted %(num)d records.", deleted
        ) % {"num": deleted}

    return Action(
        DELETE_SELECTED_NAME,
        handler,
        label=N_("Delete selected"),
        confirm=N_("Delete the selected records? This cannot be undone."),
        permission="delete",
        where="list",
    )
