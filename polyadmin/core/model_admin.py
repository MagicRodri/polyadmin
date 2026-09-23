"""ModelAdmin: the central per-resource abstraction.

Resource identity, field resolution, the CRUD lifecycle hooks, search, filters,
ordering, pagination, relations, actions, exports, and template resolution all
live here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from polyadmin.core._async import maybe_await
from polyadmin.core.action import DELETE_SELECTED_NAME, Action, action, collect_actions
from polyadmin.core.auth import Principal
from polyadmin.core.field import Field
from polyadmin.core.inline import Inline
from polyadmin.core.query import DEFAULT_EMPTY_VALUE
from polyadmin.i18n import N_, gettext, ngettext


@dataclass
class Fieldset:
    """One titled group of form fields. A title of None renders the group
    with no header, which is how the undeclared default renders as a plain
    flat form. `collapsed` only seeds the initial state; the group can
    always be opened.
    """

    fields: Sequence[str] = ()
    title: str | None = None
    description: str = ""
    collapsed: bool = False

    def __post_init__(self) -> None:
        self.fields = list(self.fields)


class ModelAdmin:
    """Base class for declaring how a resource is administered."""

    model: ClassVar[type]

    slug: ClassVar[str | None] = None
    # Sidebar grouping: ModelAdmins and AdminPages sharing a category
    # collapse into one section. None keeps a flat top-level link.
    category: ClassVar[str | None] = None
    # Sidebar icon name (see components/icons.html), shown flat or nested
    # inside a category's accordion alike.
    icon: ClassVar[str] = "collection"

    list_display: ClassVar[Sequence[str]] = ()
    form_fields: ClassVar[Sequence[str]] = ()
    # When set, `fieldsets` defines both the grouping and the field list:
    # get_form_fields() reports it flattened, so the form and the handler
    # agree. `form_fields` is then unused.
    fieldsets: ClassVar[Sequence[Fieldset]] = ()
    # Rendered as values, not inputs, and refused if posted anyway.
    # Override get_readonly_fields to vary by object, which is how
    # "editable on create, frozen afterwards" is expressed.
    readonly_fields: ClassVar[Sequence[str]] = ()
    # The sort applied when a request names none, in the ?sort= syntax
    # ("-field" for descending). Without one, rows arrive in whatever
    # order the data source returned, which for a dict-backed store is not
    # stable between requests.
    ordering: ClassVar[str | None] = None
    # How many rows a list page holds; None means DEFAULT_PAGE_SIZE.
    list_per_page: ClassVar[int | None] = None
    # What a read-only view shows for a None or blank value; None means
    # DEFAULT_EMPTY_VALUE.
    empty_value_display: ClassVar[str | None] = None
    search_fields: ClassVar[Sequence[str]] = ()
    detail_fields: ClassVar[Sequence[str] | None] = None
    filters: ClassVar[Sequence[Any]] = ()
    fields: ClassVar[Sequence[Field]] = ()
    # Names of the actions the detail page offers, in order. None means every
    # action whose `where` includes the detail page; a list overrides `where`
    # (so a "list" action can be named here), and [] offers none.
    detail_actions: ClassVar[Sequence[str] | None] = None
    # Removes the built-in bulk delete. Opt-out, so the default keeps it.
    disable_delete_selected: ClassVar[bool] = False
    # Child ModelAdmins whose records point back at this one, managed
    # inline on its create/detail/edit pages. See docs/inlines.md.
    inlines: ClassVar[Sequence[Inline]] = ()
    # Relation fields that render as a lookup-driven search box rather
    # than a <select> over the target's full queryset -- for relations too
    # large, or too principal-sensitive, to dump into a page.
    autocomplete_fields: ClassVar[Sequence[str]] = ()

    # The small-parity options -- see docs/lists.md and docs/model-admin.md.
    # sortable_by and list_display_links distinguish None ("unset") from []
    # ("none"); is_sortable and links_to_record apply the defaults.
    #
    # Which list columns offer a sort. None leaves every column sortable,
    # [] none of them. The restriction also holds for a hand-typed ?sort=,
    # but not for `ordering`, which is the admin's own choice.
    sortable_by: ClassVar[Sequence[str] | None] = None
    # Which list cells link to the record. None links the first column, []
    # links none, leaving the row menu as the way in.
    list_display_links: ClassVar[Sequence[str] | None] = None
    # Fills a field from others as they are typed: {"slug": ["title"]}
    # slugifies title into slug. Client-side and on the create form only,
    # so an existing record's slug is never rewritten under it.
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {}
    # Prepopulated fields whose letters are kept as they are instead of
    # transliterated to ASCII -- see polyadmin.core.slug.
    prepopulated_unicode: ClassVar[Sequence[str]] = ()
    # Adds "Save as new" to the edit form, which saves the submitted values
    # as a new record and leaves the original alone. Opt-in.
    save_as: ClassVar[bool] = False
    # Whether the list hands its search, filters, sort and page to the pages
    # reached from it, so they lead back into the list as it was left.
    preserve_filters: ClassVar[bool] = True

    can_view: ClassVar[bool] = True
    can_create: ClassVar[bool] = True
    can_update: ClassVar[bool] = True
    can_delete: ClassVar[bool] = True
    can_export: ClassVar[bool] = True

    # Shows a drag handle on the list view. Opt-in, because dragging never
    # persists: it reorders the <tr> elements on the page and reverts on
    # the next render. It is for triaging a list by hand without the
    # framework taking a position on how that order would be stored.
    enable_reordering: ClassVar[bool] = False

    list_template: ClassVar[str | None] = None
    detail_template: ClassVar[str | None] = None
    form_template: ClassVar[str | None] = None
    delete_template: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "actions" in vars(cls):
            raise TypeError(
                f"{cls.__name__}.actions is no longer supported: declare each action as a "
                "method decorated with @action (polyadmin.core.action.action). "
                "See docs/model-admin.md#actions."
            )

    def __init__(self) -> None:
        if getattr(self, "model", None) is None:
            raise TypeError(f"{type(self).__name__} must define `model`.")
        self._fields: dict[str, Field] = self._build_fields()

    def get_slug(self) -> str:
        if self.slug:
            return self.slug
        return f"{self.model.__name__.lower()}s"

    def get_verbose_name(self) -> str:
        return self.model.__name__

    def _build_fields(self) -> dict[str, Field]:
        declared = {field.name: field for field in self.fields}
        implied_names = [
            *self.list_display,
            *self.get_form_fields(),
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

    def get_form_fields(self) -> list[str]:
        if not self.fieldsets:
            return list(self.form_fields)
        names: list[str] = []
        for fieldset in self.fieldsets:
            names.extend(fieldset.fields)
        return names

    def get_readonly_fields(self, obj: Any = None) -> list[str]:
        """Fields rendering as values rather than inputs for this object. `obj` is
        None on the create form, so an override can tell creating from editing.
        """
        return list(self.readonly_fields)

    def get_page_size(self) -> int:
        """This ModelAdmin's own page size, or 0 to accept the framework
        default. See `list_per_page`."""
        return self.list_per_page or 0

    def get_empty_value(self) -> str:
        """What stands in for a None or blank value on the list and
        detail views. See `empty_value_display`."""
        return self.empty_value_display or DEFAULT_EMPTY_VALUE

    def get_default_ordering(self) -> str | None:
        return self.ordering

    def is_readonly(self, name: str, obj: Any = None) -> bool:
        return name in self.get_readonly_fields(obj)

    def get_fieldsets(self) -> list[Fieldset]:
        """Always at least one group: the form template renders groups
        unconditionally, so "none declared" means one unnamed group holding
        every form field, not zero groups holding nothing.
        """
        if not self.fieldsets:
            return [Fieldset(fields=list(self.form_fields))]
        return list(self.fieldsets)

    def get_detail_fields(self) -> list[str]:
        if self.detail_fields is not None:
            return list(self.detail_fields)
        return list(dict.fromkeys([*self.list_display, *self.get_form_fields()]))

    def get_actions(self) -> list[Action]:
        """The @action methods, in definition order, with the built-in bulk
        delete last -- the destructive action should not be the first thing in
        the listbox. `disable_delete_selected` and `can_delete = False` remove
        it however it is defined."""
        actions = collect_actions(self)
        others = [a for a in actions if a.name != DELETE_SELECTED_NAME]
        if self.disable_delete_selected or not self.can_delete:
            return others
        return [*others, *(a for a in actions if a.name == DELETE_SELECTED_NAME)]

    def get_action(self, name: str) -> Action | None:
        for candidate in self.get_actions():
            if candidate.name == name:
                return candidate
        return None

    def get_list_actions(self) -> list[Action]:
        """The actions the list page's bulk bar offers."""
        return [a for a in self.get_actions() if a.where in ("list", "both")]

    def get_detail_actions(self) -> list[Action]:
        """The actions one record's detail page offers. delete_selected is a
        bulk action, so it is never among them -- not by `where`, not by being
        named in `detail_actions`, not when a ModelAdmin overrides it."""
        candidates = [a for a in self.get_actions() if a.name != DELETE_SELECTED_NAME]
        if self.detail_actions is None:
            return [a for a in candidates if a.where in ("detail", "both")]
        by_name = {a.name: a for a in candidates}
        return [by_name[name] for name in self.detail_actions if name in by_name]

    def validate_detail_actions(self) -> None:
        known = {a.name for a in self.get_actions()}
        for name in self.detail_actions or ():
            if name not in known:
                raise ValueError(
                    f"{type(self).__name__}.detail_actions names {name!r}, which is not one of its actions {sorted(known)}."
                )

    @action(
        label=N_("Delete selected"),
        confirm=N_("Delete the selected records? This cannot be undone."),
        permission="delete",
        where="list",
    )
    async def delete_selected(self, objects: Sequence[Any], principal: Principal | None) -> str | None:
        """The bulk delete every admin gets for free.

        This is the single most common action anyone would otherwise write
        by hand. It is expressed entirely in terms of this ModelAdmin's own
        `delete` hook, so it works against whatever storage the application
        has and honours whatever that hook already does (cascades, soft
        deletes, hooks of its own).

        permission="delete", not the resource's bare "view": the action route
        checks it on top, so a principal who may look at a list but not destroy
        its rows is refused -- and, because the same check drives the listbox,
        never offered it in the first place.
        """
        deleted = 0
        for obj in objects:
            try:
                await maybe_await(self.delete(obj))
            except Exception as exc:
                # Stop at the first failure and report how far it got:
                # silently continuing would leave the user unable to
                # tell which records survived.
                # Translators: a bulk delete stopped part-way. %(deleted)d of
                # %(total)d records were deleted; %(error)s is the underlying error.
                failure = gettext("Deleted %(deleted)d of %(total)d, then failed: %(error)s")
                raise RuntimeError(failure % {"deleted": deleted, "total": len(objects), "error": exc}) from exc
            deleted += 1
        return ngettext("Deleted %(num)d record.", "Deleted %(num)d records.", deleted) % {"num": deleted}

    def get_template_candidates(self, view: str) -> list[str]:
        """Template lookup order for a view: an explicit `{view}_template`
        override, then a resource-specific template, then the framework
        default.
        """
        candidates: list[str] = []
        explicit = getattr(self, f"{view}_template", None)
        if explicit:
            candidates.append(explicit)
        candidates.append(f"admin/resource/{self.get_slug()}/{view}.html")
        candidates.append(f"admin/resource/{view}.html")
        return candidates

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
        raise NotImplementedError(f"{type(self).__name__} must implement delete().")

    def validate(self, data: dict[str, Any]) -> dict[str, list[str]]:
        """Run field-level validation over form data. Returns name -> errors."""
        errors: dict[str, list[str]] = {}
        for name in self.get_form_fields():
            field_errors = self.get_field(name).validate(data.get(name))
            if field_errors:
                errors[name] = field_errors
        return errors
