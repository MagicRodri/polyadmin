# Permissions

`Authorizer` answers one question — *can this principal do this thing
to this resource* — for every route and every control the templates
render.

```python
class Authorizer(Protocol):
    def can(self, principal: Any, permission: str, resource: Any = None) -> bool: ...
```

## Permission names

`resource_permission(slug, action)` builds `"{slug}.{action}"` — `"users.view"`, `"users.delete"`,
`"organizations.export"`, and so on — for the five standard actions
(`view`, `create`, `update`, `delete`, `export`), plus `"dashboard.view"`
for the dashboard route. An Action's own `permission=`
(see [`model-admin.md`](model-admin.md#actions)) is checked the same
way, as `"{slug}.{that permission}"`, alongside the resource's `.view`.
Applications are free to invent their own permission strings beyond
these standard ones — `Authorizer.can` just receives whatever
string it's asked about.

`resource` is the `ModelAdmin` (or, for relation-target checks, the
*target* `ModelAdmin`) being asked about — pass it through to your own
permission logic if it needs resource-level context (e.g. row-level
rules), or ignore it for a simpler role-based check.

A custom `AdminPage` (see [`routing.md`](routing.md#custom-admin-pages))
follows the same shape: its permission defaults to
`"page.<path-with-dots>"` and is checked as
`Authorizer.can(principal, page.permission, page)` — the `AdminPage`
itself passed as `resource` — before its handler ever runs. Pass
`permission=` at registration to use a
different string.

## Where it's enforced

Every route runs authorization server-side, unconditionally, before
any `ModelAdmin` code executes — this is the actual security boundary.
Independently of that, computed per-request permissions
(`compute_permissions`) also flow into the
template context, so Edit/Delete/Create/Export controls simply don't
render when the current principal can't use them. Both happen from the
same `Authorizer.can` calls — the UI hiding is a courtesy that follows
from the same decision, never a separate, weaker check that could
drift out of sync with the route enforcement.

Relation fields get the same treatment: a foreign-key value only
renders as a clickable link to the target resource if the principal
has `{target_slug}.view` — otherwise it falls back to plain,
unlinked text. This is checked against the *target* `ModelAdmin`'s
permissions, not the resource currently being viewed.

## Per-object permissions

The `resource` argument an `Authorizer` receives is **either the
ModelAdmin or the record itself**, depending on how much is known when
the question is asked:

1. Before a record is fetched, the check is coarse — "may this principal
   update Users at all?" — and `resource` is the ModelAdmin. Rejecting
   here means an unauthorized request never costs a lookup.
2. Once the record is loaded, the same permission is asked again with
   `resource` set to that record — "may they update *this* user?"

So a rule like "you may edit only your own record" is expressed by
inspecting what you were handed:

```python
def can(self, principal, permission, resource=None):
    if not isinstance(resource, User):
        return True    # coarse check: nothing to judge yet, decide later
    return resource.email == principal.email
```

Returning `True` for the coarse case is the important half: denying
there would block the route before the record — and therefore the real
decision — was ever reached.

The narrow check runs on the detail page, the edit form, the edit POST,
and all three delete routes. The same answer also drives the controls a
record's own pages show, so a record you may view but not change simply
has no Edit button.

## Built-in implementations

Same caveat as [`authentication.md`](authentication.md)'s built-in
`Authenticator`s — fine for local development and tests, not for a
real deployment:

- `AllowAllAuthorizer()` — grants every permission unconditionally.
- `DenyAllAuthorizer()` — denies every permission; useful for asserting
  a gate actually blocks something.
- `SuperuserAuthorizer()` — grants every permission to a `Principal`
  with `is_superuser` set, denies everyone else. Note that this is
  genuinely all-or-nothing: a signed-in non-superuser is refused
  *every* permission, `dashboard.view` included, and meets a bare
  "Permission denied." on every page. For anything with more than one
  kind of user, write an `Authorizer` that distinguishes reads from
  writes — `examples/fastapi/session.py`'s `ReadOnlyForNonSuperusers`
  is the smallest example.

## No authorizer configured

Same as with no `Authenticator`: every permission is granted by
default if `Admin` has no `authorizer` set at all. Set one before anything resembling production traffic.
