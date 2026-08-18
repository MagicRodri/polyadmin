"""Field abstraction.

A Field represents a model property plus its admin presentation, not
merely an HTML input. Context-aware rendering (list/detail/form/filter)
is added in Phase 2; this module defines the data-level contract that
rendering will build on.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from polyadmin.core.relation import Relation

_UNSET = object()


class Field:
    """Base class for all admin field types."""

    field_type: str = "field"

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        required: bool = False,
        readonly: bool = False,
        disabled: bool = False,
        default: Any = _UNSET,
        help_text: str = "",
        placeholder: str = "",
        validators: Sequence[Callable[[Any], None]] = (),
    ) -> None:
        self.name = name
        self.label = label or name.replace("_", " ").title()
        self.required = required
        self.readonly = readonly
        self.disabled = disabled
        self.default = default
        self.help_text = help_text
        self.placeholder = placeholder
        self.validators = list(validators)

    @property
    def has_default(self) -> bool:
        return self.default is not _UNSET

    def get_value(self, obj: Any) -> Any:
        """Read this field's value off a model instance."""
        value = getattr(obj, self.name, _UNSET)
        if value is _UNSET:
            return self.default if self.has_default else None
        return value

    def parse_form_value(self, raw: Any) -> Any:
        """Coerce a raw submitted form value into this field's Python
        type. An empty string becomes None for every field type so that
        `required` validation (which treats None and "" the same) still
        fires; adapters are responsible for feeding booleans in as
        checkbox presence rather than a raw string.
        """
        if raw is None or raw == "":
            return None
        if self.field_type == "integer":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return raw
        if self.field_type == "decimal":
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw
        if self.field_type == "json":
            import json

            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return raw
        return raw

    def validate(self, value: Any) -> list[str]:
        """Run configured validators, returning a list of error messages."""
        errors: list[str] = []
        if self.required and (value is None or value == ""):
            errors.append(f"{self.label} is required.")
            return errors
        for validator in self.validators:
            try:
                validator(value)
            except ValueError as exc:
                errors.append(str(exc))
        return errors

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.name!r})"


class StringField(Field):
    field_type = "string"


class TextField(Field):
    field_type = "text"


class IntegerField(Field):
    field_type = "integer"


class DecimalField(Field):
    field_type = "decimal"


class BooleanField(Field):
    field_type = "boolean"


class DateField(Field):
    field_type = "date"


class DateTimeField(Field):
    field_type = "datetime"


class EmailField(Field):
    field_type = "email"


class URLField(Field):
    field_type = "url"


class UUIDField(Field):
    field_type = "uuid"


class EnumField(Field):
    field_type = "enum"

    def __init__(self, name: str, *, choices: Sequence[Any], **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.choices = list(choices)


class JSONField(Field):
    field_type = "json"


class PasswordField(Field):
    field_type = "password"


class ForeignKeyField(Field):
    """A single related object. `get_value` returns the
    related object itself (or None), not a scalar -- rendering resolves
    its display label via `relation.display_field` on the target
    ModelAdmin.
    """

    field_type = "foreignkey"

    def __init__(self, name: str, *, relation: Relation, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.relation = relation


class OneToOneField(ForeignKeyField):
    field_type = "onetoone"


class ManyToManyField(Field):
    """A collection of related objects."""

    field_type = "manytomany"

    def __init__(self, name: str, *, relation: Relation, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.relation = relation

    def get_value(self, obj: Any) -> Any:
        value = super().get_value(obj)
        return value if value is not None else []
