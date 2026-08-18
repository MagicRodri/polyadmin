# Inline related records

A parent `ModelAdmin` can show and manage a child `ModelAdmin`'s
records that point back at it, right on the parent's own
create/detail/edit pages — Django-admin `StackedInline`/`TabularInline`
style. `Relation` (see [`model-admin.md`](model-admin.md#relations))
only models the *forward* direction (a child field pointing at its
parent); `Inline` is the reverse.

```python
from polyadmin.core.inline import TabularInline

class OrganizationAdmin(ModelAdmin):
    model = Organization
    inlines = [TabularInline("users", "organization")]
```

```go
BaseModelAdmin{
    DeclaredInlines: []core.Inline{core.NewTabularInline("users", "Organization")},
}
```

`child` is the target `ModelAdmin`'s slug; `fk_field`/`FKField` is the
name of the field on the *child* that points back at this parent (the
same field a `ForeignKeyField`/`OneToOneField` + `Relation` already
declares on the child, targeting this parent's own slug). Both are
validated once at router-mount time (`create_router`/`Mount`), after
every `ModelAdmin` is registered: a bad `fk_field` (missing, not a
FK/OneToOne field, or targeting the wrong `ModelAdmin`) raises
`ValueError`/returns an `error` immediately, rather than failing
silently at request time.

## `StackedInline` vs `TabularInline`

Layout is presentation-only — both share the same routes, permissions,
and field set, so there's one `Inline` type with a `layout`/`Layout`
discriminator, not two structurally different classes:

- **`StackedInline`** — each child rendered as its own bordered
  mini-form, fields labeled and stacked vertically.
- **`TabularInline`** — one HTML table, one row per child, fields as
  columns, a compact fit for a handful of simple fields.

```python
from polyadmin.core.inline import StackedInline, TabularInline
```

```go
core.NewStackedInline(child, fkField string, opts ...core.InlineOption) core.Inline
core.NewTabularInline(child, fkField string, opts ...core.InlineOption) core.Inline
```

Pass `label=`/`core.WithInlineLabel(...)` to override the section's
heading; it otherwise defaults to the child's own verbose name,
pluralized (`"Users"`).

## Which fields show

An inline row always shows *all* of the child's own
`form_fields`/`FormFieldNames`, minus the one `fk_field` (implied by
context — never rendered as its own input, auto-set to the parent's
primary key on every create/update). There's no way to show a curated
subset in this version: a subset would desync from the child's own
`validate()`, which iterates every one of `form_fields` and would
flag a field excluded from the inline row as spuriously missing.

## Generated routes

See [`routing.md`](routing.md#inline-routes) for the three routes
(`POST .../inlines/{child_slug}`, `POST .../inlines/{child_slug}/{child_pk}`,
`DELETE .../inlines/{child_slug}/{child_pk}`) and why there's no
`GET .../inlines/{child_slug}` fragment route. Every inline mutation
— add, edit, remove — is its own independent request with its own
save/delete action; there's no Django-formset-style batch save that
commits every row together with the parent form.

## The three page modes

- **Create page** — the parent has no primary key yet, so a child
  can't be pointed at it. The section renders as a disabled
  placeholder ("Save {Parent} to add {Children}") with no add/edit
  controls. Full management becomes available the moment you're on
  the edit page — reached immediately after creating, via the same
  `_continue`/default-redirect flow every resource already uses.
- **Edit page** — every current child renders as an editable row (per
  `layout`), each with its own Save + Remove; one persistent blank row
  at the end lets you add another. A failed add/edit re-renders just
  that one row with the submitted values and field errors, the same
  422-on-validation-failure convention every other form on this
  framework already follows.
- **Detail page** — read-only. Each child renders using its own
  `detail_fields`/`DetailFields`, linking to that child's own detail
  page (permission-gated the same way an ordinary relation link is —
  see [`permissions.md`](permissions.md#where-its-enforced)); no
  add/edit/remove controls here.

## Permissions

Viewing the section at all requires the *child's* own `.view`
permission — if the principal can't view the child resource, the whole
section is omitted, not just its controls (same principle as
relation-link hiding elsewhere in the framework). Add/edit/remove each
require the child's own `.create`/`.update`/`.delete` respectively,
**and** implicitly the parent's own `.update` — inline management only
exists on the parent's edit page, which is already gated by that
route. See [`permissions.md`](permissions.md#permission-names).

## Current limitations

- **One inline per child slug per parent.** A parent can declare
  multiple inlines (e.g. Organization → Users *and* Organization →
  Contracts), but not two inlines pointing at the same child
  `ModelAdmin`. Not validated beyond the duplicate-slug check at
  mount time — there's no disambiguating name yet.
- **No field subsetting** — see above.
- **No formset/batch-save** — see above.
- **No pagination of inline rows.** A parent with a very large number
  of children renders them all; there's no page-size cap on the inline
  query the way the top-level list view has.
