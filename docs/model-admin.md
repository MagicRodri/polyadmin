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

## Default ordering

Without one, rows arrive in whatever order the data source returned —
which for a map- or dict-backed store is not even stable between two
requests. Declare a default and the list has a defined order until the
user sorts it themselves:

```go
OrderingDefault: "-CreatedAt",   // "-" for descending, like ?sort=
```
```python
ordering = "-created_at"
```

An explicit `?sort=` from the user always wins. The default is resolved
into the request before the query runs, so a `ListPage`/`list_page`
implementation is told about it too rather than having to know the
ModelAdmin's own configuration.

## Acting on more than one page

A bulk action normally receives the rows the user ticked, which can only
ever be rows on the current page. When a whole page is selected the
table offers **"Select all N matching"**, which posts the current
search/filters instead of a pk list; the framework then resolves that
same query server-side and hands the action every matching record.

Nothing is needed to enable it. Two things are worth knowing when
writing an action: it may now receive far more objects than a page's
worth, and the set is exactly what the user was looking at — filters
included, pagination excluded.

## Scaling the list: resolving the query yourself

By default `GetQueryset`/`get_queryset` returns **everything**, and the
framework applies search, filters, ordering and pagination in memory
over that result. That is the right trade for a small collection and the
reason getting started needs one method — but it means page 40 of a
million rows costs the same as page 1, and filters make it worse rather
than better, since they run after the whole set has been loaded.

A ModelAdmin backed by a real data source can take over the whole query
by implementing one optional method:

```go
func (a *UserAdmin) ListPage(ctx context.Context, req core.ListRequest) ([]any, int, error) {
    offset, limit := req.Window()          // limit 0 means "no limit"
    // ... one query: WHERE from req.Search/req.Filters,
    //     ORDER BY from req.Ordering, LIMIT/OFFSET from the window
    return rows, total, nil
}
```
```python
def list_page(self, list_request):
    offset, limit = list_request.window()   # limit 0 means "no limit"
    ...
    return rows, total
```

Return the rows for the requested window, and the **total matching rows
before it** — that count is what pagination displays.

Three things are worth knowing:

- **It is all-or-nothing.** When this method exists the framework
  applies nothing further: it cannot tell what you already did, and
  re-applying would filter twice. Honour every part of the request, or
  the UI will show controls that do nothing.
- **It serves every list query, not just the list page.** Both exports,
  the autocomplete lookup and non-autocomplete relation option lists all
  go through it. They are distinguished purely by the window: the list
  view asks for one page, the lookup for a capped page, and an export
  or an option list sets `Unlimited`/`unlimited`, which yields a limit
  of 0. If you ignore the window, an export still works but the
  autocomplete will return your whole table.
- **`GetQueryset` is not called at all** for such an admin. It can stay
  as-is for other callers, or become a stub.

Not implementing it changes nothing: the in-memory path is unchanged.

## Grouping the form: fieldsets

By default a form is one flat column in `FormFieldNames`/`form_fields`
order. Past about eight fields that stops being readable, so fields can
be grouped into titled sections — Django's `fieldsets`:

```go
DeclaredFieldsets: []core.Fieldset{
    {Fields: []string{"Email", "IsActive"}},
    {Title: "Membership", Description: "Where this user belongs.",
        Fields: []string{"Plan", "Organization"}},
    {Title: "Advanced", Fields: []string{"APIKey"}, Collapsed: true},
},
```

```python
fieldsets = [
    Fieldset(fields=["email", "is_active"]),
    Fieldset(title="Membership", description="Where this user belongs.",
             fields=["plan", "organization"]),
    Fieldset(title="Advanced", fields=["api_key"], collapsed=True),
]
```

Three rules are worth knowing:

- **Declaring fieldsets replaces the flat field list.** The groups *are*
  the form's fields, in the order given, so `FormFields()` /
  `get_form_fields()` reports the flattened result and the handler
  parses exactly what was rendered. `FormFieldNames`/`form_fields` is
  ignored once fieldsets are set — one source of truth, not two.
- **A group with no title renders bare** — no header, no border. That is
  what makes the default case (no fieldsets declared, one implicit
  unnamed group) identical to the flat form, and it lets you keep a few
  lead fields ungrouped above the titled sections.
- **A titled group is always collapsible.** `Collapsed`/`collapsed` only
  decides whether it *starts* closed; the reader can always open it.

## Read-only fields

A field can be shown on the form as a value rather than a control:

```go
ReadOnlyFieldNames: []string{"CreatedAt"},
```
```python
readonly_fields = ["created_at"]
```

**This is enforced, not just presented.** The field renders with no
input, and the handler skips the name when reading the posted form — so
a crafted POST naming it cannot write it. (A `required` read-only field
is also excluded from validation, since the form never sends it.)

For the common "editable when created, frozen afterwards" case, override
the resolver instead of the list — it receives the object being edited,
and `nil`/`None` when creating:

```go
func (a *UserAdmin) ReadOnlyFields(obj any) []string {
    if obj == nil {
        return nil          // free to set at creation
    }
    return []string{"Email"}
}
```
```python
def get_readonly_fields(self, obj=None):
    return [] if obj is None else ["email"]
```

Note this is a different thing from a `Field`'s own `ReadOnly`/`readonly`
option, which marks a native input `readonly` but still posts its value.

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
  Python; `core.NewBooleanFilter(name)` in Go). They render behind a
  single **Filters** button in the list toolbar, which opens a
  right-hand drawer listing every filter vertically — Django admin's
  filter column, in the drawer form Unfold gives it. Each choice is a
  link that toggles one filter while preserving the others, so
  filtering works with JS off, and the trigger carries a count of how
  many are currently applied. One trigger stays one trigger however
  many filters a `ModelAdmin` declares.
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

A `ManyToManyField`/`FieldTypeManyToMany` renders as a searchable
multi-select (`ui/multi-select.html`): a Command-style list you can
type at, with the current selection as removable chips — the same job
Django admin's `filter_horizontal` permissions widget does. Its
filtering is client-side, because a many-to-many's options are already
in the page in full; that also means it is *not* the control for a
target with thousands of rows (there is no many-to-many equivalent of
`autocomplete_fields` yet). It posts one value per selection under the
field's own name, exactly as a `<select multiple>` did, so nothing on
the server side changes.

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
