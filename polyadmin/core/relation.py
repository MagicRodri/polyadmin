"""Relation: a ForeignKey/OneToOne/ManyToMany field's link to another
ModelAdmin.

A relation knows how to resolve: which ModelAdmin the related
object(s) belong to (`target`, a slug looked up on the registry at
render time -- never a direct reference, so relations don't force
import-order coupling between ModelAdmins), which of the target's
fields to show as the display label, and how many related objects
there are.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ONE = "one"  # ForeignKey / OneToOne: a single related object (or None)
MANY = "many"  # ManyToMany: a collection of related objects


class Relation:
    def __init__(
        self,
        name: str,
        *,
        target: str,
        display_field: str = "id",
        cardinality: str = ONE,
        get_related: Callable[[Any], Any] | None = None,
    ) -> None:
        self.name = name
        self.target = target
        self.display_field = display_field
        self.cardinality = cardinality
        self.get_related = get_related

    def get_value(self, obj: Any) -> Any:
        if self.get_related is not None:
            return self.get_related(obj)
        return getattr(obj, self.name, None)
