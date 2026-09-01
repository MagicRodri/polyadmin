# Authentication

`Authenticator` turns an inbound request into a `Principal` (or `None`
if unauthenticated) — that's the entire contract. It runs once per
request, before authorization or any route logic.

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

`request` is intentionally untyped — PolyAdmin's core doesn't know or
care whether the adapter hands it a FastAPI `Request` or anything else;
only the adapter (and your own `Authenticator` implementation) needs to
agree on that.

## Wiring one in

```python
admin = Admin(
    model_admins=[...],
    authenticator=MySessionAuthenticator(),
    authorizer=SuperuserAuthorizer(),
)
```

`Principal.extra` is a free-form bag for whatever your own `Authorizer`
needs beyond `is_superuser` (roles, team IDs, scopes, ...) — the core
never reads it itself.

## Built-in implementations

Two, **for local development and tests only** — neither belongs
anywhere near a real deployment:

- `AllowAllAuthenticator(principal)` — authenticates every request as
  the same fixed `Principal`.
- `DenyAllAuthenticator()` — authenticates nobody, useful for asserting
  a login gate actually blocks access.

## The login page

PolyAdmin ships the login *page* — the form, the failure message, the
CSRF check, the redirect back to wherever the visitor was headed. It
does not ship a session store or a credential check, because it does not
own identity (that is this document's whole premise) and because never
minting a session token is what keeps the framework out of key
management: it has no signing secret, and needs none.

The two halves therefore split like this:

| | reads a session | creates one |
|---|---|---|
| protocol | `Authenticator` | `LoginBackend` |
| method | `authenticate(request)` | `verify_credentials` / `begin_session` / `end_session` |

```python
sessions = CookieSessionBackend()          # your implementation
admin = Admin(authenticator=sessions, login_backend=sessions, ...)
```

One object usually implements both, since they have to agree on the
session format. `begin_session` and `end_session` receive the outgoing
response as their last argument, so a cookie-backed implementation has
something to set the cookie on. A complete, runnable implementation —
PBKDF2 password hashing, an HMAC-signed cookie — is in
`examples/fastapi/session.py`; copy it and replace the in-memory user
table.

**Registering a `login_backend` is the switch.** With one:

- `{base_path}/login` and `{base_path}/logout` are mounted. Both are
  reachable without a session — requiring one to reach the page that
  creates it is a loop — and both are CSRF-protected like any other
  route.
- An unauthenticated request is **redirected** to the login page
  instead of getting a bare 401, carrying `?next=` so signing in
  resumes where the visitor was going. HTMX requests get `HX-Redirect`,
  so an expired session navigates the window rather than swapping a
  login form into a table cell.
- The sidebar's user menu grows a **Sign out** item. It POSTs: a logout
  reachable by `GET` is one any `<img src>` on the internet can fire at
  a signed-in administrator.

Without one, none of the above exists and an unauthenticated request
gets `401`.

The `?next=` destination is validated (`safe_next_url`) to be a path
inside the admin. A `next` echoed into a `Location` header unchecked is
an open redirect: it lets an attacker use your own domain to bounce
someone somewhere hostile *after* a real, successful login. Anything
off-site, scheme-relative, or outside `base_path` falls back to the
admin's home.

Two requirements the framework asks of a `LoginBackend`, both of which
it cannot enforce for you:

- **Compare passwords in constant time**, and hash even when the
  account does not exist. Returning early on an unknown user makes it
  measurably faster than a wrong password, which turns the form into an
  account enumerator.
- **Do not distinguish "no such user" from "wrong password"** in what
  you return. The admin renders one message for both; a backend that
  leaks the difference undoes that.

## No authenticator configured

If `Admin` isn't given an `authenticator` at all, every request is
treated as authenticated (with a `None` principal) — this isn't a secure
default to deploy with, but it means you can start building
`ModelAdmin`s against an unauthenticated admin and wire up real auth
later without every route already 401ing.

## What happens on failure

If `Authenticator.authenticate` returns `None`, the adapter responds
`401 Unauthorized` before any `ModelAdmin` code runs — or redirects to
the login page, if a `login_backend` is configured (see above). A
`Principal` that authenticates successfully but fails the subsequent
authorization check (see [`permissions.md`](permissions.md)) gets
`403 Forbidden` instead — the two failure modes are distinguished
deliberately, same as any standard web framework's auth stack.

## CSRF protection

The adapter protects every mutating route — anything that isn't `GET`,
`HEAD`, `OPTIONS` or `TRACE` — with a double-submit CSRF token. It is on
by default and needs no configuration.

On every request the admin mints a token (32 random bytes as unpadded
base64url) into an `HttpOnly` cookie, and requires the same value back on
unsafe requests. Three names matter:

| Name | Where |
| --- | --- |
| `admin_csrf` | the cookie, `HttpOnly`, `SameSite=Lax`, scoped to the admin's base path |
| `X-CSRF-Token` | the request header, used by every htmx request |
| `_csrf` | the hidden form field, used by forms that submit without JavaScript |

The framework's own pages carry the token three ways: a
`<meta name="csrf-token">` tag for scripts, a hidden `_csrf` field on the
forms that can submit without JavaScript, and an `htmx:configRequest`
listener that attaches the header to every mutating `hx-*` request —
including the bodyless `hx-delete`s, which have no form field to carry
one.

Verification is wired as a custom `APIRoute` class rather than a
dependency: a dependency's response headers are dropped when a handler
returns a `Response` directly, which the admin's handlers do throughout.

The cookie is `HttpOnly` precisely because the token reaches JavaScript
through the meta tag instead, so a script that leaks the DOM does not
also leak a value usable from another origin.

### Behind a proxy

The cookie's `Secure` attribute follows the request's scheme: set over
HTTPS, unset over plain HTTP — otherwise the reference app would break
on a LAN address, since a `Secure` cookie isn't sent over HTTP at all. A
TLS-terminating proxy must therefore forward `X-Forwarded-Proto` and the
app must be configured to trust it, or the cookie will be issued without
`Secure` on a site that is in fact HTTPS.

### Custom admin pages

A custom page that renders its own `<form>` and posts it must include the
token, or the post will be rejected with `403`:

```jinja
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

```python
admin = Admin(model_admins=[...], disable_csrf=True)
```

There is no opt-in switch, only this opt-out: a security control that
defaults to off is one nobody turns on.
