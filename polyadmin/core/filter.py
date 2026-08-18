"""Filter: a list-view constraint the user can toggle.

`filter.apply(objects, raw_value, model_admin)` is deliberately given
the raw, still-a-string query-param value -- parsing is the filter's
job, since only it knows what its own values mean.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class Filter:
    def __init__(self, name: str, *, label: str | None = None):
        self.name = name
        self.label = label or name.replace("_", " ").title()

    def choices_with_labels(self) -> list[tuple[str, str]]:
        """(value, label) pairs for a <select>, "" always meaning "no filter"."""
        raise NotImplementedError

    def apply(self, objects: list[Any], raw_value: str, model_admin: Any) -> list[Any]:
        raise NotImplementedError


class BooleanFilter(Filter):
    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [("", "All"), ("true", "Yes"), ("false", "No")]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field(self.name)
        want = raw_value.lower() in ("true", "1", "on", "yes")
        return [obj for obj in objects if bool(field.get_value(obj)) == want]


class ChoiceFilter(Filter):
    def __init__(self, name: str, *, choices: Sequence[Any], label: str | None = None):
        super().__init__(name, label=label)
        self.choices = list(choices)

    def choices_with_labels(self) -> list[tuple[str, str]]:
        return [("", "All")] + [(str(choice), str(choice)) for choice in self.choices]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field(self.name)
        return [obj for obj in objects if str(field.get_value(obj)) == raw_value]
