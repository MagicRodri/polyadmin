# Authentication

`Authenticator` turns an inbound request into a `Principal` (or
`None`/`nil` if unauthenticated) — that's the entire contract. It runs
once per request, before authorization or any route logic, in both
languages.

```python
class Authenticator(Protocol):
    def authenticate(self, request: Any) -> Principal | None: ...

@dataclass
class Principal:
    id: Any
    display_name: str = ""
    is_superuser: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
```

```go
type Authenticator interface {
	Authenticate(request any) *Principal
}

type Principal struct {
	ID          any
	DisplayName string
	IsSuperuser bool
	Extra       map[string]any
}
```

`request` is intentionally untyped/`any` — PolyAdmin's core doesn't
know or care whether the adapter hands it a FastAPI `Request`, a
Fiber `*fiber.Ctx`, or anything else; only the adapter (and your own
`Authenticator` implementation) needs to agree on that.

## Wiring one in

```python
admin = Admin(
    model_admins=[...],
    authenticator=MySessionAuthenticator(),
    authorizer=SuperuserAuthorizer(),
)
```

```go
admin := core.New(
	core.WithModelAdmins(...),
	core.WithAuthenticator(MySessionAuthenticator{}),
	core.WithAuthorizer(core.SuperuserAuthorizer{}),
)
```

`Principal.extra`/`Principal.Extra` is a free-form bag for whatever
your own `Authorizer` needs beyond `is_superuser` (roles, team IDs,
scopes, ...) — PolyAdmin's core never reads it itself.

## Built-in implementations

Both languages ship two, **for local development and tests only** —
neither belongs anywhere near a real deployment:

- `AllowAllAuthenticator(principal)` / `core.NewAllowAllAuthenticator(principal)`
  — authenticates every request as the same fixed `Principal`. This is
  what both reference apps use to skip building a real login flow.
- `DenyAllAuthenticator` / a `nil`-authenticating stand-in — authenticates
  nobody, useful for asserting a login gate actually blocks access.

There is no built-in login form, session store, or credential check in
either language — PolyAdmin integrates with whatever authentication
your host application already has, rather than owning identity itself.
Write your own `Authenticator` against your session/JWT/OAuth/IAM
layer and hand it to `Admin`/`core.New`.

## No authenticator configured

If `Admin`/`core.New` isn't given an `authenticator`/`Authenticator`
at all, every request is treated as authenticated (with a `nil`
principal) — this isn't a secure default to deploy with, but it means
you can start building `ModelAdmin`s against an unauthenticated admin
and wire up real auth later without every route already 401ing.

## What happens on failure

If `Authenticator.authenticate` returns `None`/`nil`, the adapter
responds `401 Unauthorized` before any `ModelAdmin` code runs. A
`Principal` that authenticates successfully but fails the subsequent
authorization check (see [`permissions.md`](permissions.md)) gets
`403 Forbidden` instead — the two failure modes are distinguished
deliberately, same as any standard web framework's auth stack.
