"""ModelAdmin: the central per-resource abstraction.

Resource identity, field resolution, the CRUD lifecycle hooks
(get_queryset / get_object / create / update / delete), search,
filters, ordering, pagination, relations, actions, exports, and
template resolution all live here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from polyadmin.core.field import Field
from polyadmin.core.inline import Inline


class ModelAdmin:
    """Base class for declaring how a resource is administered."""

    model: ClassVar[type]

    slug: ClassVar[str | None] = None
    # Sidebar grouping: ModelAdmins (and AdminPages, see core/page.py)
    # sharing a category collapse into one accordion section, in
    # first-registration-appearance order. None keeps today's flat
    # top-level nav link.
    category: ClassVar[str | None] = None
    # Sidebar-nav icon name (see templates/admin/components/icons.html)
    # shown next to this ModelAdmin's own link, whether it renders flat
    # or nested inside a category's accordion.
    icon: ClassVar[str] = "collection"

    list_display: ClassVar[Sequence[str]] = ()
    form_fields: ClassVar[Sequence[str]] = ()
    search_fields: ClassVar[Sequence[str]] = ()
    detail_fields: ClassVar[Sequence[str] | None] = None
    filters: ClassVar[Sequence[Any]] = ()
    fields: ClassVar[Sequence[Field]] = ()
    actions: ClassVar[Sequence[Any]] = ()
    # Reverse-relation declarations: child ModelAdmins whose records
    # point back at this one, managed/displayed inline on this
    # ModelAdmin's create/detail/edit pages. See core/inline.py and
    # docs/inlines.md.
    inlines: ClassVar[Sequence[Inline]] = ()
    # Relation (foreignkey/onetoone) form fields that render as a
    # lookup-driven search box instead of a <select>
    # populated from the target's full queryset -- for relations too
    # large, or too principal-sensitive, to dump wholesale into a page.
    autocomplete_fields: ClassVar[Sequence[str]] = ()

    can_view: ClassVar[bool] = True
    can_create: ClassVar[bool] = True
    can_update: ClassVar[bool] = True
    can_delete: ClassVar[bool] = True
    can_export: ClassVar[bool] = True

    # Shows a drag handle on this ModelAdmin's list view. Defaults to
    # False (opt-in), unlike can_*/*_template above: dragging never
    # persists anywhere -- it only reorders the <tr> elements already
    # on the page, and reverts on the next reload, sort, search, or
    # page change re-rendering the table from the server's own order.
    # It exists for admins who want to eyeball/triage a list by hand
    # without the framework taking a position on how (or whether) that
    # order is stored. Mirrors go-polyadmin's BaseModelAdmin.EnableReordering.
    enable_reordering: ClassVar[bool] = False

    list_template: ClassVar[str | None] = None
    detail_template: ClassVar[str | None] = None
    form_template: ClassVar[str | None] = None
    delete_template: ClassVar[str | None] = None

    def __init__(self) -> None:
        if getattr(self, "model", None) is None:
            raise TypeError(f"{type(self).__name__} must define `model`.")
        self._fields: dict[str, Field] = self._build_fields()

    # -- identity -----------------------------------------------------

    def get_slug(self) -> str:
        if self.slug:
            return self.slug
        return f"{self.model.__name__.lower()}s"

    def get_verbose_name(self) -> str:
        return self.model.__name__

    # -- fields ---------------------------------------------------------

    def _build_fields(self) -> dict[str, Field]:
        declared = {field.name: field for field in self.fields}
        implied_names = [
            *self.list_display,
            *self.form_fields,
            *self.search_fields,
        ]
        for name in implied_names:
            if name not in declared:
                declared[name] = Field(name)
        return declared

    def get_fields(self) -> dict[str, Field]:
        return self._fields

    def get_field(self, name: str) -> Field:
        try:
            return self._fields[name]
        except KeyError:
            raise KeyError(
                f"{type(self).__name__} has no field {name!r}; "
                f"add it to `fields`, `list_display`, or `form_fields`."
            ) from None

    def get_list_display_values(self, obj: Any) -> dict[str, Any]:
        return {name: self.get_field(name).get_value(obj) for name in self.list_display}

    def get_pk(self, obj: Any) -> Any:
        """Return the primary key used to build this object's URL."""
        return getattr(obj, "id", None)

    def get_detail_fields(self) -> list[str]:
        if self.detail_fields is not None:
            return list(self.detail_fields)
        return list(dict.fromkeys([*self.list_display, *self.form_fields]))

    def get_action(self, name: str) -> Any | None:
        for action in self.actions:
            if action.name == name:
                return action
        return None

    # -- templates ------------------------------------------------------

    def get_template_candidates(self, view: str) -> list[str]:
        """Template lookup order for a view ("list"/"detail"/"form"/"delete"):
        an explicit `{view}_template` override, then a resource-specific
        template, then the framework default.
        """
        candidates: list[str] = []
        explicit = getattr(self, f"{view}_template", None)
        if explicit:
            candidates.append(explicit)
        candidates.append(f"admin/resource/{self.get_slug()}/{view}.html")
        candidates.append(f"admin/resource/{view}.html")
        return candidates

    # -- CRUD lifecycle ---------------------------------------------------

    def get_queryset(self) -> Any:
        """Return the base, unfiltered collection of records for this resource."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement get_queryset()."
        )

    def get_object(self, pk: Any) -> Any:
        """Fetch a single record by primary key, or None if not found."""
        raise NotImplementedError(f"{type(self).__name__} must implement get_object().")

    def create(self, data: dict[str, Any]) -> Any:
        """Create and persist a new record from validated form data."""
        raise NotImplementedError(f"{type(self).__name__} must implement create().")

    def update(self, obj: Any, data: dict[str, Any]) -> Any:
        """Apply validated form data to an existing record and persist it."""
        raise NotImplementedError(f"{type(self).__name__} must implement update().")

    def delete(self, obj: Any) -> None:
        """Delete an existing record."""
        raise NotImplementedError(f"{type(self).__name__} must implement delete().")

    # -- validation ---------------------------------------------------

    def validate(self, data: dict[str, Any]) -> dict[str, list[str]]:
        """Run field-level validation over form data. Returns name -> errors."""
        errors: dict[str, list[str]] = {}
        for name in self.form_fields:
            field_errors = self.get_field(name).validate(data.get(name))
            if field_errors:
                errors[name] = field_errors
        return errors
