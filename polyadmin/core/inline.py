"""Inline: a reverse-relation admin declaration -- lets a parent
ModelAdmin manage/display a child ModelAdmin's records that point back
at it via one FK/OneToOne field. See docs/inlines.md.

`layout` is presentation-only, not behavioral, so there is one Inline
type with a layout discriminator, not two structurally different
classes -- StackedInline/TabularInline are just layout-preset
subclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from polyadmin.core._async import maybe_await
from polyadmin.core.query import ListRequest, alist_objects

if TYPE_CHECKING:
    from polyadmin.core.model_admin import ModelAdmin

STACKED = "stacked"
TABULAR = "tabular"


class Inline:
    """child is the target (child) ModelAdmin's slug; fk_field is the
    name of the field on the child that points back at this parent.
    """

    def __init__(
        self,
        child: str,
        fk_field: str,
        *,
        layout: str = STACKED,
        label: str | None = None,
    ) -> None:
        self.child = child
        self.fk_field = fk_field
        self.layout = layout
        # None -> the adapter derives a label from the child's own
        # verbose name (needs the Admin registry, so resolved there).
        self.label = label


class StackedInline(Inline):
    def __init__(self, child: str, fk_field: str, *, label: str | None = None) -> None:
        super().__init__(child, fk_field, layout=STACKED, label=label)


class TabularInline(Inline):
    def __init__(self, child: str, fk_field: str, *, label: str | None = None) -> None:
        super().__init__(child, fk_field, layout=TABULAR, label=label)


async def afilter_inline_children(
    child_admin: ModelAdmin, fk_field: str, parent_admin: ModelAdmin, parent_pk: Any
) -> list[Any]:
    """Children of `child_admin` that point at the object identified by
    `parent_pk` on `parent_admin`.

    A child that implements `list_page` answers for itself: it is asked for
    every row (`unlimited`) with `filters[fk_field] = str(parent_pk)` and its
    rows are used as returned, so an HTTP-backed child never has to download
    its whole table to be filtered here. That is the contract such a child
    implements. Any other child loads its queryset (which may be async) and is
    filtered in memory by its fk field: PKs compare as strings to dodge int/str
    mismatches, and the fk field's value is the related object itself (per
    Relation.get_value), so `parent_admin.get_pk(...)` resolves its PK.
    """
    if hasattr(child_admin, "list_page"):
        objects, _ = await alist_objects(
            child_admin, ListRequest(filters={fk_field: str(parent_pk)}, unlimited=True)
        )
        return list(objects)
    field = child_admin.get_field(fk_field)
    parent_pk_str = str(parent_pk)
    result = []
    for obj in await maybe_await(child_admin.get_queryset()):
        related = field.get_value(obj)
        if related is None:
            continue
        if str(parent_admin.get_pk(related)) == parent_pk_str:
            result.append(obj)
    return result


# How many options a tabular inline's many-to-many listbox shows before
# it scrolls. Four keeps the row close to the height of the single-line
# controls beside it, which is what makes the table read as rows rather
# than as stacked blocks.
INLINE_MULTISELECT_ROWS = 4
