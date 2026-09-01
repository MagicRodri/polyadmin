# Templates

How rendering works, and how to override a template.

## Three-level override resolution

`Renderer(template_dirs=(...))` searches, in order: any directories
you pass in `template_dirs` (searched in the order given), then the
framework's own `polyadmin/templates/`. Within that search path, each
view resolves through `ModelAdmin.get_template_candidates(view)`:

1. An explicit override — `list_template`/`detail_template`/
   `form_template`/`delete_template` set on your `ModelAdmin` subclass.
2. A resource-specific template — `admin/resource/{slug}/{view}.html`.
3. The framework default — `admin/resource/{view}.html`.

```python
router = create_router(admin, base_path="/admin", template_dirs=["templates"])
```

```
templates/
└── admin/
    └── resource/
        └── users/
            └── list.html    # only replaces the Users list view
```

Jinja2's `{% extends %}`/`{% include %}` can still reach the framework
templates by name (e.g. `{% extends "admin/base.html" %}`), so an
override typically extends and overrides one block rather than starting
from scratch:

```jinja
{% extends "admin/base.html" %}
{% block content %}
<p class="mb-4">Only active accounts are shown.</p>
{% include "admin/components/list_content.html" %}
{% endblock %}
```

Custom dashboard widgets get the same treatment through the same
option: a widget whose `template` name isn't one of the built-ins is
looked up across the `template_dirs` directories the same way. See
[`dashboard.md`](dashboard.md#custom-widgets).

## Custom admin page templates

A custom `AdminPage` (see [`routing.md`](routing.md#custom-admin-pages))
renders its own template, not a framework-owned one — there's no
`admin/page.html` default to fall back to, since the whole point is
application-specific markup.

It can be any template reachable through the normal `template_dirs`
search — no new resolution rule. It should
`{% extends "admin/base.html" %}` to get the shared layout (sidebar,
breadcrumbs, flash), exactly like a resource template override does:

```jinja
{% extends "admin/base.html" %}
{% block content %}
<h1>{{ page.label }}</h1>
{% endblock %}
```

## The `admin/` template namespace

The framework's own templates live under a directory literally named
`admin/` (`polyadmin/templates/admin/*.html`) — this is a template
*lookup* namespace, unrelated to the project's own name (PolyAdmin);
Django keeps the same convention for its own admin templates regardless
of how a site is branded. `{% extends "admin/base.html" %}` is internal
plumbing, not user-facing.

## The template tree

```
admin/
├── base.html                     # the shell (sidebar, breadcrumbs, flash)
├── theme.html                    # design tokens, Tailwind config, Alpine/HTMX
├── login.html                    # the one page outside the shell
├── dashboard.html
├── resource/                     # the four generated views, and where
│   ├── list.html                 #   a resource's own override goes:
│   ├── detail.html               #   admin/resource/{slug}/{view}.html
│   ├── form.html
│   └── delete.html
├── components/                   # partials the pages are assembled from
│   ├── list_content.html         #   the swappable #resource-list region
│   ├── search.html
│   ├── form_wrapper.html
│   ├── field.html                #   read-only value rendering
│   ├── icons.html
│   ├── inline.html
│   ├── inline_fragment.html
│   ├── lookup_results.html
│   ├── toasts.html
│   ├── action_confirm_modal.html
│   ├── csrf-field.html
│   └── ui/                       # the shadcn/ui ports
└── widgets/                      # dashboard widgets
```

`resource/list.html` and `resource/form.html` are deliberately thin —
each is four lines of `{% extends %}`/`{% include %}` over
`components/list_content.html` / `components/form_wrapper.html`,
because those inner regions are also rendered on their own as HTMX
fragments. Keeping them in separate files means an override can
`{% include %}` one instead of copying its markup.

## What a template gets

The `Renderer` builds a context object per view — `list_context`,
`detail_context`, `form_context`, `delete_context`, `dashboard_context`
in `core/template_context.py` — carrying: the resource's rows/fields
for that view, computed per-request permissions (so
Edit/Delete/Create/Export controls are omitted server-side when
unavailable, not just hidden with CSS), breadcrumbs, site title/logo,
and any pending flash messages. The template layer never receives the
raw `ModelAdmin` object's storage internals — only what the view
actually needs to render.

## Styling

The design system is [shadcn/ui](https://ui.shadcn.com), hand-ported to
Alpine.js — see [`components.md`](components.md) for the full component
list and the porting rationale. In short:

- **Colors are tokens, never literals.** `bg-background`,
  `text-muted-foreground`, `border-input` and friends resolve through
  CSS variables declared in `admin/theme.html`. No template names a
  Tailwind shade like `neutral-500`, which is what makes the admin
  themeable and gives it dark mode for free.
- **Class lists come from `ui(...)`**, the server-side stand-in for
  shadcn's `class-variance-authority`: `{{ ui('button', 'outline', 'size-sm') }}`
  composes a base with a variant and a size, while `{{ ui('table', 'th') }}`
  resolves a sub-component's own list. The registry lives in
  `polyadmin/ui.py`.
- **Radix is replaced by Alpine, not shipped.** Focus trapping is
  `x-trap`, portals are `x-teleport`, popover positioning is `x-anchor`,
  collapse is `x-collapse`. There is no React and no Radix runtime.
- **Controls that gain nothing from a listbox stay native** — checkbox,
  radio, range, `<input type="date">`, and `<select multiple>`
  (manytomany) are styled to match shadcn rather than replaced by a
  Radix-style widget. A single-value `<select>` (enum fields, a plain
  foreignkey/onetoone) is the one exception: it's `ui/select.html`, a
  real trigger+listbox port with a hidden input carrying the posted
  value, matching the bulk-actions listbox and the relation combobox's
  own reasoning. The other genuinely Alpine-driven ports are the
  relation combobox, the date picker's calendar popover, the dialog,
  the dropdown menu, the sheet, and the toasts.
- **A few components predate the port** (the toast queue, the confirm
  dialog) and came from [PinesUI](https://devdojo.com/pines); they were
  restyled onto the same tokens rather than rewritten.

Tailwind, Alpine (plus its focus/collapse/anchor plugins), and HTMX are
all CDN-loaded from `admin/theme.html` — there is no frontend build step
to run.

### Dark mode

`admin/theme.html` resolves the theme in a synchronous inline script
before first paint (so a dark reload doesn't flash light), toggling a
`dark` class on `<html>`, and exposes an `Alpine.store('theme')` that
the header's toggle button drives. The preference persists in
`localStorage` under `polyadmin-theme`; with nothing stored it follows
`prefers-color-scheme`.

To restyle the whole admin, override `admin/theme.html` and change the
CSS variables — nothing else needs to know.
