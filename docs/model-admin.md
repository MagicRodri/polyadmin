# ModelAdmin

`ModelAdmin` is the abstraction you actually write: one subclass per
resource, declaring how it should be administered and how to read/
write it. This is the reference for that contract — identity, fields,
the CRUD lifecycle, search/filter/ordering, relations, and Actions.

## Declaring one

**Python** — class attributes plus `Field` instances:

```python
from polyadmin import ModelAdmin, EmailField, BooleanField
from polyadmin.core.field import ForeignKeyField
from polyadmin.core.relation import Relation

class UserAdmin(ModelAdmin):
    model = User
    list_display = ("id", "email", "is_active", "organization")
    form_fields = ("email", "is_active", "organization")
    search_fields = ("email",)
    fields = (
        EmailField("email", required=True),
        BooleanField("is_active", default=True),
        ForeignKeyField("organization", relation=Relation(
            "organization", target="organizations", display_field="name",
        )),
    )

    def get_queryset(self):
        return self.repository.list()

    def get_object(self, pk):
        return self.repository.get(int(pk))

    def create(self, data):
        return self.repository.create(**data)

    def update(self, obj, data):
        return self.repository.update(obj, **data)

    def delete(self, obj):
        self.repository.delete(obj)
```

**Go** — `BaseModelAdmin` embedded, fields built with functional
options, CRUD hooks implemented as methods on your own type:

```go
type UserAdmin struct {
	core.BaseModelAdmin
	repository *UserRepository
}

func NewUserAdmin(repository *UserRepository) *UserAdmin {
	return &UserAdmin{
		BaseModelAdmin: core.BaseModelAdmin{
			ModelName:      "User",
			DisplayFields:  []string{"ID", "Email", "IsActive", "Organization"},
			FormFieldNames: []string{"Email", "IsActive", "Organization"},
			SearchFieldNames: []string{"Email"},
			DeclaredFields: []core.Field{
				core.NewField("Email", core.FieldTypeEmail, core.WithRequired()),
				core.NewField("IsActive", core.FieldTypeBoolean, core.WithDefault(true)),
				core.NewField("Organization", core.FieldTypeForeignKey,
					core.WithRelation(core.Relation{Name: "Organization", Target: "organizations", DisplayField: "Name"})),
			},
		},
		repository: repository,
	}
}

func (a *UserAdmin) GetQueryset(ctx context.Context) (any, error) {
	users := a.repository.List()
	out := make([]any, len(users))
	for i, u := range users {
		out[i] = u
	}
	return out, nil // must be []any -- see the note below
}

func (a *UserAdmin) GetObject(ctx context.Context, pk any) (any, error) { /* ... */ }
func (a *UserAdmin) Create(ctx context.Context, data map[string]any) (any, error) { /* ... */ }
func (a *UserAdmin) Update(ctx context.Context, obj any, data map[string]any) (any, error) { /* ... */ }
func (a *UserAdmin) Delete(ctx context.Context, obj any) error { /* ... */ }
```

> **Go gotcha:** `GetQueryset` must return `[]any`, not a concrete
> `[]*User` — the Fiber adapter's list/detail/relation-option code
> can't implicitly convert between slice types. Build the `[]any` by
> hand as shown above.

## Identity

- `slug`/`SlugOverride` — the URL segment (`/admin/{slug}`); defaults
  to the lowercased, pluralized model name (`user` → `users`).
- `get_verbose_name()`/`VerboseName()` — the human-readable name shown
  in the sidebar, breadcrumbs, and page titles; defaults to the model
  name as declared.
- `get_pk(obj)`/`GetPK(obj)` — the primary key used to build this
  object's URL; defaults to reading an `id`/`ID` field/attribute.
- `category`/`NavCategory` — optional sidebar grouping; ModelAdmins
  (and custom `AdminPage`s) sharing a category collapse into one
  collapsible accordion section, in first-registration-appearance
  order. Unset (`None`/`""`) keeps today's flat top-level nav link.
  Also prepended to the breadcrumb trail when set. See
  [`routing.md`](routing.md#sidebar-categories).
- `icon`/`NavIcon` — the sidebar-nav icon shown next to this
  ModelAdmin's own link, flat or nested inside a category's accordion;
  defaults to `"collection"`. See
  [`routing.md`](routing.md#sidebar-categories).

## Fields

A field's `name` must match either an attribute on your model object
(Python) or a struct field/map key (Go, via `structFieldOrMapValue`).
Every field the resource uses anywhere (`list_display`, `form_fields`,
`search_fields`) needs a `Field` declaration; Python fills in a plain
untyped `Field` automatically for any name it doesn't find one
declared for, so declaring one explicitly is only required when you
need type-specific behavior (validation, a `<select>` of choices, a
relation).

Built-in Python field types: `StringField`, `TextField`,
`IntegerField`, `DecimalField`, `BooleanField`, `DateField`,
`DateTimeField`, `EmailField`, `URLField`, `UUIDField`, `EnumField`,
`JSONField`, `PasswordField`, `ForeignKeyField`, `OneToOneField`,
`ManyToManyField`. Go equivalents are `core.FieldType*` constants
passed to `core.NewField(name, fieldType, opts...)` (`FieldTypeString`,
`FieldTypeInteger`, `FieldTypeBoolean`, `FieldTypeForeignKey`, ...).

Common options (Python keyword args / Go `With*` functional options):
`required`/`WithRequired()`, `readonly`/`WithReadonly()`,
`disabled`/`WithDisabled()`, `default=`/`WithDefault(v)`,
`help_text=`/`WithHelpText(s)`, `placeholder=`/`WithPlaceholder(s)`.

## The CRUD lifecycle

Five hooks, all of which you implement against your own storage —
neither language's core ever issues a database query:

| Hook | Called for |
|---|---|
| `get_queryset()` / `GetQueryset(ctx)` | list view, before search/filter/order/paginate |
| `get_object(pk)` / `GetObject(ctx, pk)` | detail, edit, delete, and Action target resolution |
| `create(data)` / `Create(ctx, data)` | POST create, after validation passes |
| `update(obj, data)` / `Update(ctx, obj, data)` | POST edit, after validation passes |
| `delete(obj)` / `Delete(ctx, obj)` | POST/DELETE delete |

`data` is a `dict[str, Any]` / `map[string]any` keyed by field name,
already coerced to each field's Python/Go type (an `IntegerField`
submission arrives as `int`, a `BooleanField` as `bool`, and so on).

## Validation

`validate(data)`/`Validate(data)` runs every `form_fields` field's own
validators (required-ness first, then any custom `validators=`/
per-field checks) and returns a `dict[str, list[str]]` /
`map[string][]string` of field name → error messages. A non-empty
result re-renders the form with those errors instead of calling
`create`/`update` — `ModelAdmin.Create`/`Update` are only ever called
with data that already passed validation.

## Search, filters, ordering

- `search_fields`/`SearchFieldNames` — a case-insensitive substring
  match against these fields, OR'd together, driven by the list view's
  search box.
- `filters`/`DeclaredFilters` — a sequence of `Filter` objects
  (`BooleanFilter(name)`, `ChoiceFilter(name, choices=[...])` in
  Python; `core.NewBooleanFilter(name)` in Go) rendered as a
  Django-admin-style right-hand panel of links, each toggling one
  filter while preserving the others.
- Any column in `list_display` is sortable by clicking its header;
  `?sort=name` / `?sort=-name` for ascending/descending.

All three compose: the query pipeline applies search, then every
active filter, then ordering, then pagination — in that order, every
time, so a query string fully determines what's on screen (and what
an export produces, see [`exports.md`](exports.md)).

`enable_reordering`/`EnableReordering` (default `False`/`false`, unlike
the `can_*`/`Disable*` flags above) puts a drag handle on the list
view's rows via a small vanilla sortable library (SortableJS,
`theme.html`). Unlike everything else on this page, dragging never
persists anywhere — it only reorders the `<tr>` elements already on the
current page, and reverts on the next reload, sort, search, or page
change re-rendering the table from the server's real order. It's for
triaging a list by hand, not for maintaining a stored position; an
application wanting persisted ordering needs its own position field and
its own way of writing to it (there's no framework hook for this, since
it can't presume your schema).

## Relations

A `ForeignKeyField`/`FieldTypeForeignKey` (or `OneToOneField`) needs a
`Relation`: which target `ModelAdmin` slug it points at and which of
the target's fields to use as the display label. By default it
renders as a shadcn Select (`ui/select.html`) populated from the
target's full queryset on the form, and as a link (if the viewer can
see the target resource, otherwise plain text) on the list/detail
views.

Add the field's name to `autocomplete_fields`/`AutocompleteFieldNames`
to switch the form input to a searchable shadcn/ui Combobox-style
combobox instead, backed by `GET /{slug}/lookup?q=...` — the target's
full queryset is never loaded into the page, only whatever the search
matches (up to 20 results) plus the current selection. Use this for
any relation whose target could grow large, or where dumping the
whole list would leak more than the viewer should see.

A relation's *reverse* side — showing/managing a child's records from
the parent's own create/detail/edit pages, Django-admin
StackedInline/TabularInline style — is `Inline`. See
[`inlines.md`](inlines.md).

## Actions

Actions (record actions from the detail page, bulk actions from the
list view's row-selection) share one type — see
`admin.core.action.Action` / `core.Action`:

```python
from polyadmin.core.action import Action

def deactivate(model_admin, objects, principal):
    for obj in objects:
        obj.is_active = False
    return f"Deactivated {len(objects)} user(s)."  # flash message text

class UserAdmin(ModelAdmin):
    actions = [Action("deactivate", deactivate, confirm="Deactivate the selected users?")]
```

```go
core.NewAction("deactivate", func(ctx context.Context, ma core.ModelAdmin, objects []any, p *core.Principal) (string, error) {
	for _, obj := range objects {
		obj.(*User).IsActive = false
	}
	return fmt.Sprintf("Deactivated %d user(s).", len(objects)), nil
}, core.WithActionLabel("Deactivate"), core.WithActionConfirm("Deactivate the selected users?"))
```

An action handler is always called with a list of objects — one for a
detail-page record action, as many as were checked for a bulk action —
so it never needs to know which UI entry point invoked it. On the list
view, picking one from the bulk-actions listbox runs it immediately —
there's no separate "Apply" step. `confirm=`/
`WithActionConfirm(...)` shows a shadcn/ui Dialog before the request goes
out; `permission=`/`WithActionPermission(...)` checks an extra
`{slug}.{permission}` permission (see
[`permissions.md`](permissions.md)) beyond the resource's own `.view`.
The handler's return value (a string, or `None`/`""`) becomes the
success toast text, falling back to `"{label} applied to N record(s)."`
when empty.

## Templates

`list_template`/`detail_template`/`form_template`/`delete_template`
(Python only — see [`templates.md`](templates.md) for the override
resolution order and the Go adapter's current limitation there).
