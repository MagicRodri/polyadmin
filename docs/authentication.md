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

## CSRF protection

Both adapters protect every mutating route — anything that isn't `GET`,
`HEAD`, `OPTIONS` or `TRACE` — with a double-submit CSRF token. It is on
by default and needs no configuration.

On every request the admin mints a token (32 random bytes as unpadded
base64url) into an `HttpOnly` cookie, and requires the same value back on
unsafe requests. Three names are shared by both languages:

| Name | Where |
| --- | --- |
| `admin_csrf` | the cookie, `HttpOnly`, `SameSite=Lax`, scoped to the admin's base path |
| `X-CSRF-Token` | the request header, used by every htmx request |
| `_csrf` | the hidden form field, used by forms that submit without JavaScript |

The framework's own pages carry the token three ways: a
`<meta name="csrf-token">` tag for scripts, a hidden `_csrf` field on the
four forms that can submit without JavaScript, and an
`htmx:configRequest` listener that attaches the header to every mutating
`hx-*` request — including the bodyless `hx-delete`s, which have no form
field to carry one.

The cookie is `HttpOnly` precisely because the token reaches JavaScript
through the meta tag instead, so a script that leaks the DOM does not
also leak a value usable from another origin.

### Behind a proxy

The cookie's `Secure` attribute follows the request's scheme: set over
HTTPS, unset over plain HTTP — otherwise the reference apps would break
on a LAN address, since a `Secure` cookie isn't sent over HTTP at all. A
TLS-terminating proxy must therefore forward `X-Forwarded-Proto` and the
app must be configured to trust it, or the cookie will be issued without
`Secure` on a site that is in fact HTTPS.

### Custom admin pages

A custom page that renders its own `<form>` and posts it must include the
token, or the post will be rejected with `403`:

```html
{{/* Go */}}
{{template "csrf-field" .CSRFToken}}
```

```html
{# Python #}
{% from "admin/components/csrf-field.html" import csrf_field %}
{{ csrf_field(csrf_token) }}
```

A form that only ever submits via `hx-post`/`hx-get` needs neither: the
listener adds the header, and without JavaScript such a form never
submits at all.

### Clickjacking headers

Every admin response also carries `X-Frame-Options: DENY` and
`Content-Security-Policy: frame-ancestors 'none'`. These are not part of
the CSRF opt-out below — framing is a different attack from forgery.

### Opting out

If your host application already provides CSRF protection for the whole
site, you can turn the verification off. The token cookie is still minted
and the templates still render it, so nothing else changes:

```go
admin := core.New(core.WithModelAdmins(...), core.WithCSRFDisabled())
```

```python
admin = Admin(model_admins=[...], disable_csrf=True)
```

There is no opt-in switch, only this opt-out: a security control that
defaults to off is one nobody turns on.
