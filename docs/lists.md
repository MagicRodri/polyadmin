# The list view

Beyond search, filters, sorting and pagination, four options shape how a
list behaves and where it leads. All four are opt-in except the first,
which is on because the alternative — losing a reader's filters the
moment they open a record — is rarely what anyone wants.

## Keeping the reader's place

Open a record from a filtered list, save it, and you land back in that
list, with the search, filters, sort and page you left. This is on by
default:

```python
class OrganizationAdmin(ModelAdmin):
    # Off, if you'd rather always land on the bare list.
    preserve_filters = False
```

**How it travels.** The list's links carry one reserved parameter,
`_list`, holding the list's own path and query; the create, edit and
delete forms post it back in a hidden field of the same name. Because it
rides in the page rather than in the browser's history, it survives "Save
and continue editing", a bookmark and a new tab.

Note where it actually shows up. This admin returns you to the
**record's own page** after a save, not to the list, so the token's real
job is to travel with you: the detail page, the edit form and the create
form all carry it, and the **breadcrumb back to the list** is the link
that uses it. Only a delete returns to the list directly.

A token that is not a path under the admin's own base is discarded and
you get the bare list — the same rule `safe_redirect_path` applies to a
`Referer`.

## Which columns sort

By default every column in `list_display` offers a sort. Restrict it
when a column is computed, or expensive, or simply meaningless to order
by:

```python
class UserAdmin(ModelAdmin):
    list_display = ["id", "email", "plan", "last_seen"]
    sortable_by = ["id", "email"]
```

A column outside the list renders as a plain header, with no sort menu.
The restriction is also enforced server-side: `?sort=plan` is dropped and
the default ordering applies, so a hand-typed URL cannot reach it either.

`None` means "every column"; an empty list means "none". `ordering` is
exempt — it is the admin's own choice, not user input, so an admin may
sort by a column it does not offer as a header.

## Which cells open the record

The first column links to the record. Name others — or none — with
`list_display_links`:

```python
class UserAdmin(ModelAdmin):
    list_display_links = ["email"]  # the address, not the id
```

An empty list links nothing and leaves the row menu as the
only way in. A cell whose value is already a link — a relation, chiefly
— is never wrapped in a second one.

## Filtering by date

A date or datetime field gets the windows a reader actually asks for --
"what came in this week?" -- by declaring a filter, like any other:

```python
from polyadmin.core.filter import DateFilter

class OrganizationAdmin(ModelAdmin):
    filters = [DateFilter("founded")]
```

It renders in the same filter panel as `BooleanFilter` and
`ChoiceFilter`, and offers **Any date**, **Today**, **Past 7 days**,
**This month** and **This year**. The value in the URL is the preset's
own name (`filter[founded]=7d`), so a filtered list is a link like any
other.

Below the presets the panel offers **Custom range**, two date inputs
whose value rides in the same parameter:

```
?filter[founded]=7d                       a preset
?filter[founded]=2026-01-01:2026-03-01    a range
?filter[founded]=2026-01-01:              from that date through today
```

The range is **inclusive of both endpoints** — that is what "from X to
Y" means — and `date_filter_range` converts it to the same half-open
window the presets produce, so a `list_page` implementation resolving
the raw value gets identical results either way. An empty end means
"through today", resolved by the parser rather than by the panel, so the
range still works with scripting off. An empty start, an unparseable
date, or an end before its start narrows nothing, the same rule an
unrecognised preset follows.

Because it rides in the same `ListRequest` as every other filter,
**exports and `delete_selected` narrow with it**: "all N matching" means
what the panel is showing.

A `list_page` implementation resolves it in its own query.
`date_filter_range` turns a value into the half-open window the in-memory
path applies, so the two cannot drift:

```python
from polyadmin.core.filter import date_filter_range

class OrganizationAdmin(ModelAdmin):
    def list_page(self, list_request):
        window = date_filter_range(list_request.filters.get("founded", ""), datetime.now())
        if window:
            start, end = window
            where.append("founded >= %s AND founded < %s")
            args += [start, end]
        ...
```

Two details worth knowing: the window is **half-open** (`>= from`,
`< to`), so a row on the boundary belongs to exactly one window; and it
is compared **by date**, so a datetime's clock time never decides whether
it counts as "today". An unrecognised value narrows nothing rather than
failing, so a crafted URL renders the list unfiltered.

## Filtering on whether a field is set at all

`EmptyFilter` splits a list on presence, which is the question behind
most "why is this record wrong?" hunts:

```python
class UserAdmin(ModelAdmin):
    filters = [EmptyFilter("organization")]
```

It offers **All**, **Empty** and **Not empty**, and the URL carries
`filter[organization]=empty` or `=notempty`.

**Empty means unset or blank, never merely zero.** `None`, `""`, an
empty collection and a zero datetime are empty; `0`, `False` and `"0"`
are values somebody chose. A `many` relation is empty when it has no
members.

A `list_page` implementation reads the raw value and compares it against
the constants, so the two paths cannot drift:

```python
value = request.filters.get("organization")
if value == EMPTY_FILTER_EMPTY:
    where.append("organization_id IS NULL")
elif value == EMPTY_FILTER_NOT_EMPTY:
    where.append("organization_id IS NOT NULL")
```

## Filtering by a related record

```python
class UserAdmin(ModelAdmin):
    filters = [RelationFilter("organization")]
```

The URL carries the target's primary key —
`filter[organization]=3` — and a `many` relation matches when any member
does, so "users whose teams include Platform" works.

**The control follows `autocomplete_fields`.** A relation named there
renders as the same lookup-backed combobox the form uses, pointed at the
target's own `/lookup` route; every other relation renders as a list of
links over the target's whole queryset, uncapped, exactly as the form's
non-autocomplete `<select>` already does. Declaring the relation in
`autocomplete_fields` is the answer to a large target, and it is the
same answer in both places.

A reader who may not view the target resource does not get the filter at
all — it is dropped from the panel rather than shown empty.

**One limitation worth knowing.** `apply` receives the parent
ModelAdmin, not the registry, so it cannot call the target's own
`get_pk`. It uses the same default lookup `ModelAdmin.get_pk` does. If
the target declares its own, pass `related_pk` to match:

```python
RelationFilter("organization", related_pk=lambda related: related.code)
```

## Writing your own filter

A filter is a base class, not a closed set. Subclass `Filter`, implement
two methods and declare it like any built-in; Django calls this a
`SimpleListFilter`, and the two halves are the same: the options, and
the constraint.

```python
class PlanFilter(Filter):
    def choices_with_labels(self):
        return [("", "All"), ("paid", "Paid"), ("free", "Free")]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects  # "" always means "no filter"
        field = model_admin.get_field("plan")
        return [
            obj for obj in objects if (field.get_value(obj) != "Free") == (raw_value == "paid")
        ]
```

```python
class UserAdmin(ModelAdmin):
    filters = [PlanFilter("plan")]
```

Three rules make a host filter equal to a built-in rather than
cosmetic:

- **`""` always means "no filter".** It is the first choice, it is what
  Clear all sets, and `apply` must return its input unchanged for it.
- **An unrecognised value narrows nothing.** The value comes from a URL,
  so treat anything you do not recognise as absent rather than failing —
  a crafted link should render the list, not an error.
- **`apply` gets the raw string.** Parsing is the filter's own job,
  because only it knows what its values mean.

Because it rides in the same `ListRequest` as every built-in, **exports
and `delete_selected` narrow with it**: "all N matching" means what the
panel is showing. A `list_page` implementation reads the same raw value
out of `request.filters` and resolves it in its own query.

A filter that needs a control other than a list of links says so with
`control_kind` — that is how `DateFilter` gets its range inputs and
`RelationFilter` its combobox. A filter that leaves it alone is a choice
list, which is what almost every filter wants.
