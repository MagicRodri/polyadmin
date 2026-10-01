# Bulk editing

A ModelAdmin that lists `bulk_edit_fields` gets an **Edit selected** action
on its list page. It changes the same fields on every selected record in one
go:

```python
class UserAdmin(ModelAdmin):
    form_fields = ["email", "is_active", "plan", "organization"]
    bulk_edit_fields = ["is_active", "plan", "organization"]
```

Each name must be one of the form fields and not in `readonly_fields`; a
wrong name fails when the `Admin` is built. The action is offered only when
`can_update` is true, and it requires the `{slug}.update` permission on top
of `.view`. It is a list-only action: it never appears on a detail page, even
when named in `detail_actions`.

## The form

Picking **Edit selected** opens a form with one row per field, using the
field's own widget — the same select, switch or relation picker the edit form
shows, including `autocomplete_fields`. Each row has a **Change** checkbox,
and the field stays disabled until it is ticked. Only ticked fields are
parsed, validated and applied; a row left unticked is ignored even when a
value is posted for it. Submitting with nothing ticked redisplays the form
with "Choose at least one field to change."

## `update` receives only the ticked fields

The default implementation calls your ModelAdmin's own `update(obj, data)`
once per record, with `data` holding **only the ticked fields** — a PATCH,
not the full form the edit page posts. An `update` that reads every key and
writes what it finds would clear the fields nobody touched:

```python
def update(self, obj, data):
    obj.plan = data.get("plan")                    # wipes plan when it was not ticked
    if "plan" in data:                             # keeps it
        obj.plan = data["plan"]
```

Write `update` so that a missing key leaves the value as it is. The edit form
already omits read-only fields, so an `update` that handles that is most of
the way there.

## One call instead of N

Override `bulk_update` to apply the change in a single call, for example to a
backend's bulk endpoint:

```python
class EmployeeAdmin(ModelAdmin):
    bulk_edit_fields = ["group"]

    async def bulk_update(self, objects, data, principal):
        await self.client.patch("/employees", json={"ids": [o.id for o in objects], **data})
        return f"Updated {len(objects)} employee(s)."
```

The return value is the success message, as for any action.

## All or nothing

Before anything is applied, every selected record is checked: the
authorizer must allow `{slug}.update` on that record, and none of the ticked
fields may be read-only for it (`get_readonly_fields(obj)`). If any record
fails either check, nothing is changed and the form lists the records that
blocked it.

The default loop stops at the first record whose `update` raises and reports
how far it got — "Updated 3 of 10, then failed: …" — the same way the bulk
delete does. Records before the failure keep their change; there is no
transaction to roll back. Override `bulk_update` when your storage can do
better.

## Audit log

Each record gets an ordinary `update` entry, the same as saving it from its
edit page (see [`audit`](audit.md)).

## Replacing the built-in

`bulk_edit` is a method on `ModelAdmin` decorated with `@action`, like
`delete_selected`. Override it to change its label or behaviour, and repeat
the decorator to keep it a form action:

```python
class UserAdmin(ModelAdmin):
    bulk_edit_fields = ["plan"]

    @action(label="Change plan", form=lambda ma: ma.get_bulk_edit_form(), permission="update", where="list")
    async def bulk_edit(self, objects, principal, data):
        ...
```
