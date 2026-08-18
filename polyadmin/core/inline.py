"""Inline: a reverse-relation admin declaration -- lets a parent
ModelAdmin manage/display a child ModelAdmin's records that point back
at it via one FK/OneToOne field, Django-admin TabularInline/StackedInline
style. See docs/inlines.md.

`layout` is presentation-only, not behavioral, so there is one Inline
type with a layout discriminator, not two structurally different
classes -- StackedInline/TabularInline are just layout-preset
subclasses, for a Django-familiar spelling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only needed for type hints -- inline.py must not import
    # model_admin.py at runtime, since model_admin.py imports Inline
    # (a real ClassVar default, not just a hint) from here. Guarding
    # only this side is enough to avoid a circular import.
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


def filter_inline_children(
    child_admin: "ModelAdmin", fk_field: str, parent_admin: "ModelAdmin", parent_pk: Any
) -> list[Any]:
    """Children of `child_admin` whose `fk_field` points at the object
    identified by `parent_pk` on `parent_admin` -- filters
    `child_admin.get_queryset()` (the whole, unfiltered collection) in
    memory, the same convention core/query.py's search/filter/ordering
    pipeline already uses. PKs compare as strings to dodge int/str
    mismatches; `fk_field`'s value is the related object itself (per
    Relation.get_value), so `parent_admin.get_pk(...)` resolves its PK.
    """
    field = child_admin.get_field(fk_field)
    parent_pk_str = str(parent_pk)
    result = []
    for obj in child_admin.get_queryset():
        related = field.get_value(obj)
        if related is None:
            continue
        if str(parent_admin.get_pk(related)) == parent_pk_str:
            result.append(obj)
    return result
