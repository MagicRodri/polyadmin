"""shadcn/ui's variant lookups, resolved server-side.

`UI_REGISTRY` is the server-side equivalent of shadcn/ui's
class-variance-authority (cva) variant objects -- see
plan/shadcnui-usage.md §6 step 3. shadcn ships each component's class
list as a JS lookup resolved at React render time; there is no JS render
step here, so the same lookup lives in Python and is resolved while the
Jinja template renders, via the `ui` global:

    {{ ui("button", "outline", "size-sm") }}
    {{ ui("table", "th") }}

Each entry splits its class lists the same way shadcn itself does:

* ``base``/``variants``/``sizes`` are the cva axes. They are *composed*:
  ``ui("button", "outline", "size-sm")`` yields
  base + variants["outline"] + sizes["size-sm"].
* ``parts`` are sub-components -- shadcn ships CardTitle, TableHead,
  BreadcrumbLink and friends as separate components with their own class
  lists, not as variants of the parent. They *replace* the base:
  ``ui("card", "title")`` yields parts["title"] alone.

Keeping the two apart matters for more than tidiness. cva composes
safely only because a base never sets a property its variants or sizes
also set (shadcn's button base carries no height, padding, or
background -- those live solely in sizes and variants), and because
React-side cva runs its output through tailwind-merge to drop conflicts.
There is no tailwind-merge here, so the discipline has to hold by
construction: two competing utilities in one class attribute resolve by
Tailwind's own output order, not the order written.
``test_base_does_not_fight_its_variants`` pins that.

Parts must never be composed with the base for the same reason -- and, in
one case, for a sharper one: ``combobox``'s "item-active" is handed to
classList.add() by the combobox's arrow-key handler, and classList.add
throws InvalidCharacterError on a value containing a space.
``test_parts_are_usable_from_classlist`` pins that.

Every class string is a token-based rewrite of the corresponding shadcn
component's own classes: colors come from the CSS variables declared in
``admin/theme.html`` (bg-background, text-muted-foreground,
border-input, ...) rather than a literal palette, which is what makes the
whole admin themeable and dark-mode-capable at once.

Sizes are prefixed ``size-`` because shadcn has a variant named
"default" *and* a size named "default"; the prefix is also how the
resolver knows which axis a caller supplied.

Mirrored by go-polyadmin/fiber/ui.go -- the two registries are kept
key-for-key identical so a template in either language can be read
against the other.
"""
from __future__ import annotations

# Each value is a dict with optional "base" (str) and optional
# "variants"/"sizes"/"parts" (dict[str, str]) keys.
UI_REGISTRY: dict[str, dict[str, object]] = {

    # -- Phase A: primitives ------------------------------------------

    "button": {
        # No height, padding, or background here -- see the uiComponent
        # note on why a base must not fight its own axes.
        "base": "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50",
        "variants": {
            # shadcn's six stock button variants, verbatim in intent.
            "default": "bg-primary text-primary-foreground hover:bg-primary/90",
            "destructive": "bg-destructive text-destructive-foreground hover:bg-destructive/90",
            "outline": "border border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground",
            "secondary": "bg-secondary text-secondary-foreground hover:bg-secondary/80",
            "ghost": "text-foreground hover:bg-accent hover:text-accent-foreground",
            "link": "text-primary underline-offset-4 hover:underline",
            # Not shadcn variants, but each has a real job here.
            # shadcn ships no destructive counterpart to `outline`, and
            # two places need one: a detail page's Delete link, which
            # sits beside an outline Edit and should match its weight
            # rather than out-shout it (solid `destructive` is reserved
            # for the actual confirmation page's submit), and a table
            # row's icon-only Delete, which wants the color with no
            # chrome at all.
            "destructive-outline": "border border-destructive/40 bg-background text-destructive hover:bg-destructive hover:text-destructive-foreground",
            "ghost-destructive": "text-destructive hover:bg-destructive/10 hover:text-destructive",
            # Low-emphasis muted ghost: the view/edit row buttons, the
            # sidebar close, the theme toggle.
            "ghost-muted": "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        },
        "sizes": {
            "size-default": "h-10 px-4 py-2",
            "size-sm": "h-9 px-3",
            "size-xs": "h-8 px-2.5 text-xs",
            "size-lg": "h-11 px-8",
            "size-icon": "h-9 w-9 shrink-0",
            "size-icon-sm": "h-8 w-8 shrink-0",
            "size-icon-xs": "h-7 w-7 shrink-0",
        },
    },

    "input": {
        "base": "flex w-full rounded-md border border-input bg-background text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        "sizes": {
            "size-default": "h-10 px-3 py-2",
            "size-sm": "h-9 px-2",
        },
        "parts": {
            # A standalone (not composed) control for an input sitting
            # inside an already-bordered wrapper -- the combobox's search
            # field -- so it contributes no border, ring, or background of
            # its own.
            "bare": "flex h-10 w-full bg-transparent p-0 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
        },
    },

    "textarea": {
        "base": "flex w-full rounded-md border border-input bg-background text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        "sizes": {"size-default": "min-h-[80px] px-3 py-2"},
    },

    # A native <select>, not shadcn's Radix-backed SelectTrigger: a
    # custom listbox does not post its value with a plain form submit,
    # and the admin's forms have to keep working without JS. Styled to
    # match the shadcn trigger (same height, border, ring).
    "select": {
        "base": "flex w-full items-center rounded-md border border-input bg-background text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        "sizes": {
            "size-default": "h-10 px-3 py-2",
            "size-sm": "h-9 px-2",
            # <select multiple> sizes itself by its `size` attribute.
            "size-auto": "h-auto px-3 py-2",
        },
    },

    "label": {
        "base": "block text-sm font-medium leading-none text-foreground peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
    },

    # Native checkbox/radio tinted with `accent-primary` (CSS
    # accent-color) rather than shadcn's Radix Checkbox, for the same
    # no-JS-form reason as select above.
    "checkbox": {
        "base": "h-4 w-4 shrink-0 rounded-sm border-input bg-background accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
    },

    "radio": {
        "base": "h-4 w-4 shrink-0 border-input bg-background accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
    },

    # Alpine-driven switch (a <button role="switch"> plus a hidden
    # input), so unlike checkbox it is a real shadcn port. "on"/"off"
    # and "thumb-on"/"thumb-off" are applied *alongside* "track"/"thumb"
    # by an Alpine :class binding, which is why neither carries a
    # background or a size of its own.
    "switch": {
        "parts": {
            "track": "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
            "on": "bg-primary",
            "off": "bg-input",
            "thumb": "pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform",
            "thumb-on": "translate-x-4",
            "thumb-off": "translate-x-0",
        },
    },

    "badge": {
        "base": "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none",
        "variants": {
            "default": "border-transparent bg-primary text-primary-foreground",
            "secondary": "border-transparent bg-secondary text-secondary-foreground",
            "destructive": "border-transparent bg-destructive text-destructive-foreground",
            "outline": "border-border text-foreground",
        },
    },

    "card": {
        "base": "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
        "parts": {
            "header": "flex flex-col gap-1.5 p-6",
            "title": "text-sm font-medium leading-none tracking-tight text-muted-foreground",
            "description": "text-sm text-muted-foreground",
            "content": "p-6 pt-0",
            "footer": "flex items-center p-6 pt-0",
        },
    },

    "alert": {
        # `border` with no color; the variants supply the color.
        "base": "relative w-full rounded-lg border p-4",
        "variants": {
            "default": "border-border bg-card text-card-foreground",
            "destructive": "border-destructive/50 bg-destructive/10 text-destructive dark:border-destructive",
        },
        "parts": {
            "title": "mb-1 text-sm font-medium leading-none tracking-tight",
            "description": "text-sm opacity-90",
        },
    },

    "separator": {
        "base": "shrink-0 bg-border",
        "variants": {
            "horizontal": "h-px w-full",
            "vertical": "h-full w-px",
        },
    },

    "skeleton": {"base": "animate-pulse rounded-md bg-muted"},

    "avatar": {
        "base": "relative flex h-9 w-9 shrink-0 overflow-hidden rounded-full bg-muted",
        "parts": {
            "image": "aspect-square h-full w-full object-cover",
            "fallback": "flex h-full w-full items-center justify-center bg-muted text-xs font-medium text-muted-foreground",
        },
    },

    # Shared text roles, so "the muted small text" is one decision
    # rather than a repeated literal in twelve templates.
    "text": {
        "parts": {
            "muted": "text-sm text-muted-foreground",
            "muted-xs": "text-xs text-muted-foreground",
            "empty": "text-sm text-muted-foreground",
            "placeholder": "text-muted-foreground",
            "heading": "text-sm font-semibold text-foreground",
            "label-caps": "text-xs font-semibold uppercase tracking-wide text-muted-foreground",
            "metric": "text-3xl font-semibold text-foreground",
            "link": "text-primary underline-offset-4 hover:underline",
            "error": "text-xs font-medium text-destructive",
        },
    },

    # -- Phase B: overlays --------------------------------------------

    "dialog": {
        "parts": {
            "overlay": "fixed inset-0 bg-black/80",
            "container": "fixed inset-0 flex items-center justify-center p-4",
            "content": "relative w-full max-w-lg rounded-lg border border-border bg-background p-6 text-foreground shadow-lg",
            "content-sm": "relative w-full max-w-sm rounded-lg border border-border bg-background p-6 text-foreground shadow-lg",
            "title": "text-base font-semibold leading-none tracking-tight text-foreground",
            "description": "mt-2 text-sm text-muted-foreground",
            "footer": "mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
        },
    },

    "dropdown": {
        "parts": {
            "content": "z-50 min-w-[10rem] overflow-hidden rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md",
            "item": "relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none",
            "label": "px-2 py-1.5 text-xs font-semibold text-muted-foreground",
            "separator": "-mx-1 my-1 h-px bg-muted",
        },
    },

    "popover": {
        "parts": {
            "content": "z-50 w-72 rounded-md border border-border bg-popover p-4 text-popover-foreground shadow-md outline-none",
        },
    },

    "tooltip": {
        "parts": {
            "content": "z-50 overflow-hidden rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground shadow-md",
        },
    },

    # Sonner is what shadcn ships for toasts now; the existing
    # PinesUI-derived queue in toasts.html already has the same shape
    # (teleported stack, per-type icon, auto-dismiss), so this is a
    # restyle of that rather than a fresh port.
    "toast": {
        "parts": {
            # ToastViewport, from shadcn/ui's Toast: pinned bottom-right
            # on sm and up, full-width along the bottom edge on a phone.
            #
            # pointer-events-none is load-bearing now that record pages
            # carry a sticky action bar in that same corner -- the
            # viewport spans a strip of the screen even with no toasts
            # in it, and would otherwise swallow clicks on Save. Each
            # toast re-enables pointer events for itself.
            "list": (
                "pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex max-h-screen "
                "flex-col gap-2 p-4 sm:inset-x-auto sm:right-0 sm:bottom-0 md:max-w-[420px]"
            ),
            "root": (
                "pointer-events-auto group relative flex w-full items-start gap-3 overflow-hidden "
                "rounded-md border border-border bg-background p-4 pr-8 text-foreground shadow-lg"
            ),
            "title": "text-sm font-semibold leading-none",
            "description": "mt-1.5 text-sm leading-snug opacity-90",
            "close": (
                "absolute right-2 top-2 rounded-md p-1 text-foreground/50 opacity-0 "
                "transition-opacity hover:text-foreground focus:opacity-100 focus:outline-none "
                "focus:ring-2 focus:ring-ring group-hover:opacity-100"
            ),
        },
    },

    "sheet": {
        "parts": {
            "overlay": "fixed inset-0 z-40 bg-black/60",
            # Deliberately carries no background or width: the sidebar
            # composes this with `ui "sidebar"`, and two competing
            # bg-*/w-* utilities resolve by Tailwind's output order rather
            # than intent. Panels that aren't the sidebar add "panel".
            "content": "fixed z-50 shadow-lg transition-transform duration-300 ease-in-out",
            "panel": "bg-background",
            "side-left": "inset-y-0 left-0 h-full border-r border-border",
            "side-right": "inset-y-0 right-0 h-full border-l border-border",
            "width-panel": "w-72",
        },
    },

    # -- Phase C: navigation & data ------------------------------------

    # Sidebar, ported from shadcn/ui's sidebar-07 block ("a sidebar that
    # collapses to icons"). The block's own --sidebar-* colour scale is
    # deliberately *not* reproduced: its Zinc values are within a hair of
    # card/accent/border, and theme.html's whole premise is that
    # restyling the admin means editing those variables and nothing
    # else. Widths match the block exactly (16rem open, 3rem collapsed,
    # 18rem for the mobile sheet).
    "sidebar": {
        "base": (
            "flex h-full shrink-0 flex-col border-r border-border bg-card "
            "transition-[width] duration-200 ease-linear"
        ),
        "parts": {
            "expanded": "w-64",
            # 3rem exactly: p-2 either side of a size-8 icon button, so
            # the icon column doesn't shift during the transition.
            "collapsed": "w-12",
            "header": "flex flex-col gap-2 p-2",
            "content": "flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden p-2",
            "footer": "flex flex-col gap-2 border-t border-border p-2",
            "group": "flex w-full min-w-0 flex-col",
            "group-label": (
                "flex h-8 shrink-0 items-center rounded-md px-2 text-xs "
                "font-medium text-muted-foreground/70"
            ),
            "menu": "flex w-full min-w-0 flex-col gap-1",
            # The sub-menu's left rule is what makes nesting legible once
            # a group is open; it has no icon column of its own.
            "menu-sub": "mx-3.5 flex min-w-0 flex-col gap-1 border-l border-border px-2.5 py-0.5",
            # SidebarRail: the hairline strip on the sidebar's edge that
            # toggles it. Invisible until hovered, hence ::after not a border.
            "rail": (
                "absolute inset-y-0 -right-2 z-20 hidden w-4 cursor-w-resize md:block "
                "after:absolute after:inset-y-0 after:left-1/2 after:w-px "
                "after:transition-colors hover:after:bg-border"
            ),
            # SidebarInset: the content column beside the sidebar.
            "inset": "relative flex min-h-0 min-w-0 flex-1 flex-col bg-background",
            # The block's h-16 header: trigger, separator, breadcrumbs.
            "topbar": "flex h-16 shrink-0 items-center gap-2 border-b border-border px-4",
        },
    },

    # SidebarMenuButton. p-2 + a size-4 icon is exactly the collapsed
    # sidebar's 3rem, so nothing shifts horizontally as it animates --
    # only the label clips away.
    "nav-item": {
        # No background here: active/inactive supply it.
        "base": "flex w-full items-center gap-2 overflow-hidden rounded-md p-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "variants": {
            "active": "bg-accent font-medium text-accent-foreground",
            "inactive": "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
        },
        "sizes": {
            # Base carries padding, not height, so these don't fight it.
            "size-default": "h-8",
            # The taller brand and user buttons at the sidebar's two ends.
            "size-lg": "h-12",
        },
    },

    "tabs": {
        "parts": {
            "list": "inline-flex h-9 items-center justify-center gap-1 rounded-lg bg-muted p-1 text-muted-foreground",
            "trigger": "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
            "trigger-on": "bg-background text-foreground shadow-sm",
            "trigger-off": "text-muted-foreground hover:text-foreground",
            # Underline flavor, for the dashboard's Tabs container widget
            # -- a pill row would fight the card it sits inside.
            "underline-list": "mb-3 flex gap-1 border-b border-border",
            "underline-trigger": "-mb-px border-b-2 px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "underline-trigger-on": "border-primary text-foreground",
            "underline-trigger-off": "border-transparent text-muted-foreground hover:text-foreground",
        },
    },

    "accordion": {
        "parts": {
            "item": "border-b border-border",
            "trigger": "flex w-full flex-1 items-center justify-between gap-3 py-3 text-sm font-medium text-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "content": "overflow-hidden pb-3 text-sm text-muted-foreground",
            "chevron": "shrink-0 transition-transform duration-200",
        },
    },

    "breadcrumb": {
        "base": "flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground",
        "parts": {
            "item": "flex items-center gap-1.5",
            "link": "rounded transition-colors hover:text-foreground",
            "page": "cursor-default font-semibold text-foreground",
            "plain": "cursor-default",
            "separator": "text-border",
        },
    },

    # Toolbar + footer of the list page's data table, ported from
    # shadcn/ui's Tasks example. The toolbar is one row: search and the
    # faceted filter dropdowns on the left, the page's own actions
    # (Export, New) on the right. The footer is the example's
    # DataTablePagination: selection count left, rows-per-page + page
    # indicator + the four jump buttons right.
    # Stacked into one full-width column until lg, a row from lg up.
    #
    # lg, not sm, because of where the sidebar lands: it's an off-canvas
    # sheet below md and a static 16rem column from md up, so the
    # content area *shrinks* at md (735px -> 549px at the breakpoint
    # itself) rather than growing. Measured, the five controls only stop
    # wrapping into a ragged three-or-four line block at ~1024px; sm
    # (640px) and md (768px) both put them in a row that immediately
    # wraps, which reads as misalignment above the table. So they stay
    # stacked, one per line, through both.
    "toolbar": {
        "base": "flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between",
        "parts": {
            # Every control inside carries its own "item" to fill its
            # line while stacked -- stretch alone can't do it, since
            # several of them are buttons wrapped in a <form> or a
            # positioning <div>.
            #
            # flex-1 so the filter cluster takes the slack and the
            # actions stay hard right once they are rows.
            "filters": "flex flex-1 flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center",
            "actions": "flex flex-col gap-2 lg:flex-row lg:items-center",
            "item": "w-full lg:w-auto",
            # A stacked control is a full-width bar, and centred content
            # in a full-width bar reads as floating: the label goes hard
            # left, the icon hard right. "item-label" takes the slack
            # (which also makes the button base's justify-center a no-op
            # while stacked -- there is no free space left to centre, so
            # the two never fight), and "item-icon" moves a *leading*
            # icon to the trailing edge without reordering the markup.
            # Both revert at lg, where the button is content-width again
            # and icon-then-label centred is right.
            "item-label": "flex-1 text-left lg:flex-none",
            "item-icon": "order-last lg:order-none",
        },
    },
    # The filter drawer, after Django admin's right-hand filter column
    # as Unfold restyles it: one Filters trigger in the toolbar, and a
    # sheet that slides in from the right listing every filter
    # vertically. One trigger stays one trigger however many filters a
    # ModelAdmin declares, which a row of per-filter dropdowns doesn't.
    "filter-panel": {
        "parts": {
            "header": "flex items-center justify-between gap-2 border-b border-border px-4 py-3",
            "title": "text-sm font-semibold text-foreground",
            "body": "flex-1 space-y-5 overflow-y-auto px-4 py-4",
            "group-label": (
                "mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            ),
            "choice": (
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors "
                "hover:bg-accent hover:text-accent-foreground"
            ),
            "choice-active": "bg-accent font-medium text-accent-foreground",
            "choice-inactive": "text-muted-foreground",
            "footer": "border-t border-border px-4 py-3",
            # The count badge on the trigger, shown only while filters
            # are actually narrowing the list.
            "count": "rounded-sm px-1 font-mono text-xs font-normal",
        },
    },

    "pagination": {
        "base": "flex flex-col items-center gap-3 sm:flex-row sm:justify-between",
        "parts": {
            "list": "flex h-9 items-center divide-x divide-border overflow-hidden rounded-md border border-border bg-card text-sm leading-tight text-muted-foreground",
            "link": "relative inline-flex h-full items-center px-3 transition-colors hover:bg-accent hover:text-accent-foreground",
            "disabled": "pointer-events-none text-muted-foreground/40",
            "current": "hidden h-full items-center px-3 font-medium text-foreground sm:flex",
            # -- Tasks-example footer --
            # The selection count, which stays visible (as "0 of N")
            # even with nothing selected, exactly as the example does.
            "selection": "flex-1 text-sm text-muted-foreground",
            "controls": "flex items-center gap-4 lg:gap-8",
            "rows-per-page": "flex items-center gap-2 text-sm font-medium",
            "page-indicator": "flex w-[100px] items-center justify-center text-sm font-medium",
            "jumps": "flex items-center gap-2",
            # The two outer jumps (first/last) are hidden on small
            # screens in the example -- prev/next are enough there.
            "jump-edge": "hidden h-8 w-8 p-0 lg:flex",
            "jump": "h-8 w-8 p-0",
        },
    },

    "table": {
        "base": "w-full min-w-full caption-bottom text-sm",
        "parts": {
            "wrapper": "overflow-hidden rounded-lg border border-border bg-card",
            "scroll": "overflow-x-auto",
            # The "select all N matching" strip: only ever visible once
            # a whole page is ticked, so it reads as a follow-up
            # question rather than permanent chrome.
            "select-all": "flex flex-wrap items-center justify-center gap-2 border-b border-border bg-muted/40 px-4 py-2 text-center text-sm text-muted-foreground",
            "select-all-action": "font-medium text-foreground underline underline-offset-2 hover:no-underline",
            "head": "[&_tr]:border-b [&_tr]:border-border",
            "th": "px-4 py-2.5 text-left align-middle font-medium whitespace-nowrap text-muted-foreground",
            "body": "divide-y divide-border",
            # data-[state=selected], from shadcn/ui's own TableRow: a
            # checked row-checkbox (list_content.html) tints the whole
            # row, the same as a hover, so a selection reads at a glance
            # instead of only through the toolbar's "N of M selected"
            # count.
            "row": "text-foreground transition-colors hover:bg-muted/50 has-[.row-checkbox:checked]:bg-muted",
            "cell": "px-4 py-2.5 align-middle text-sm whitespace-nowrap",
            "empty": "px-4 py-6 text-sm text-muted-foreground",
            # Compact flavor for the dashboard Table widget and tabular
            # inlines, which sit inside an existing card.
            "th-compact": "px-3 py-2 text-left text-xs font-medium whitespace-nowrap text-muted-foreground",
            "cell-compact": "px-3 py-2 align-middle whitespace-nowrap",
        },
    },

    # -- Phase D: forms & advanced -------------------------------------

    # The label + control + description + error unit. shadcn calls this
    # FormItem/FormLabel/FormDescription/FormMessage; here it is what
    # wraps every generated form input.
    "field": {
        "base": "mb-4",
        "parts": {
            "label": "block text-sm font-medium leading-none text-foreground",
            "required": "ml-0.5 text-destructive",
            "control": "mt-1.5",
            "description": "mt-1.5 text-xs text-muted-foreground",
            "message": "mt-1.5 text-xs font-medium text-destructive",
            # A read-only field's value, shown instead of a control.
            # Deliberately not input-shaped: a disabled-looking box
            # invites clicking at it, a plain value does not.
            "readonly": "py-1.5 text-sm text-foreground",
        },
    },

    "combobox": {
        "base": "relative",
        "parts": {
            "trigger": "flex items-center gap-2 rounded-md border border-input bg-background px-3 ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2",
            "content": "absolute z-50 mt-1 max-h-[280px] w-full overflow-y-auto rounded-md border border-border bg-popover py-1 text-sm text-popover-foreground shadow-md",
            "item": "relative flex cursor-pointer select-none items-center rounded-sm px-3 py-1.5 text-popover-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
            # Handed to classList.add()/remove() by the arrow-key
            # handler, so this must stay a single space-free class.
            "item-active": "bg-accent",
            "empty": "px-3 py-1.5 text-muted-foreground",
            "icon": "w-4 h-4 shrink-0 text-muted-foreground",
        },
    },

    # The many-to-many control: a Command-style searchable list (shadcn's
    # Combobox/Command idiom) over the relation's options, with the
    # current selection shown as removable chips on the trigger. Same job
    # as Django admin's filter_horizontal permissions widget -- the point
    # of both is that a long option list is unusable until you can type
    # at it -- without the two-pane layout, which needs width this form
    # column doesn't have.
    "multi-select": {
        "parts": {
            # min-h matches the single Select's h-10 so a field with
            # nothing chosen lines up with its neighbours; it grows from
            # there as chips wrap onto more lines.
            "trigger": "min-h-10 justify-between gap-2 text-left",
            "values": "flex flex-1 flex-wrap items-center gap-1",
            "chip": "gap-1 py-0.5 pr-1 pl-2 font-normal",
            # The chip's own remove affordance. Not a <button>: the chip
            # lives inside the trigger <button>, and HTML forbids nesting
            # one button in another.
            "chip-remove": "rounded-sm p-0.5 transition-colors hover:bg-background/60",
            "search": "flex items-center gap-2 border-b border-border px-3",
            "list": "max-h-56 overflow-y-auto py-1",
        },
    },

    "calendar": {
        "base": "w-auto p-3",
        "parts": {
            "header": "flex items-center justify-between gap-2 pb-2",
            "caption": "text-sm font-medium text-foreground",
            "nav": "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "grid": "w-full border-collapse",
            "weekday": "h-8 w-8 p-0 text-center text-[0.7rem] font-normal text-muted-foreground",
            # "day" carries no background so the three state parts below
            # can be layered on via an Alpine :class binding.
            "day": "h-8 w-8 rounded-md p-0 text-center text-sm font-normal text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "day-selected": "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            "day-today": "border border-border font-semibold",
            "day-outside": "text-muted-foreground/50",
        },
    },

    "slider": {
        "base": "relative flex w-full touch-none select-none items-center",
        "parts": {
            # A native range input, tinted with accent-color -- same
            # no-JS-form reasoning as checkbox/radio.
            "track": "h-2 w-full cursor-pointer appearance-none rounded-full bg-secondary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
            "output": "w-12 shrink-0 text-right text-sm tabular-nums text-muted-foreground",
        },
    },

    # -- dashboard / misc ---------------------------------------------

    "widget": {
        "base": "rounded-lg border border-border bg-card p-4 text-card-foreground shadow-sm sm:p-6",
        "parts": {
            "header": "mb-3 flex items-center gap-3",
            "icon": "inline-flex shrink-0 items-center justify-center rounded-lg bg-muted p-2 text-foreground",
            "title": "text-sm font-medium text-muted-foreground",
            "span-lg": "sm:col-span-2 xl:col-span-3",
            "bar-track": "h-2 w-full rounded-full bg-muted",
            "bar-fill": "h-2 rounded-full bg-primary",
        },
    },

    # Form fieldset (Django's `fieldsets`): a titled, collapsible group
    # of fields inside the record form. A group with no title renders
    # bare -- no header, no border -- so the default single-group case
    # looks exactly like the flat form it replaces.
    "fieldset": {
        "base": "mb-6 last:mb-0 rounded-lg border border-border bg-muted/20",
        "parts": {
            "trigger": "flex w-full items-center justify-between gap-2 rounded-t-lg px-4 py-3 text-left transition-colors hover:bg-muted/40",
            "title": "text-sm font-semibold text-foreground",
            "description": "px-4 pb-2 text-sm text-muted-foreground",
            "body": "border-t border-border p-4",
            "icon": "size-4 shrink-0 text-muted-foreground transition-transform",
        },
    },

    "panel": {
        "base": "rounded-lg border border-border bg-card p-4 text-card-foreground",
        "parts": {
            "dashed": "rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground",
            "form": "w-full rounded-lg border border-border bg-card p-7 text-card-foreground shadow-sm",
        },
    },
    # Record-page shell for detail/create/edit: one full-height column
    # holding the record and an action bar pinned to the bottom of the
    # viewport. Used by resource/detail.html and components/
    # form_wrapper.html so the two never disagree about width or
    # alignment.
    "page": {
        # min-h-full (not h-full) is what lets the column grow past the
        # viewport for a long record instead of clipping it.
        "base": "flex min-h-full flex-col",
        "parts": {
            # my-auto is the whole trick: while there's free space it
            # splits it above and below, centering the record
            # vertically; once the content overflows there's no free
            # space left and it collapses to 0, so the same rule gives
            # "centered when it fits, scrolls when it doesn't" without
            # a media query or any JS measuring anything.
            "body": "mx-auto my-auto w-full max-w-xl space-y-4",
            # sticky rather than fixed: it stays inside <main>'s scroll
            # container, so it needs no sidebar-width offset to avoid
            # overlapping the nav and no compensating bottom padding on
            # the content -- it reserves its own space in flow, and the
            # record scrolls underneath it. The negative margins cancel
            # <main>'s p-4 so the bar spans the full content width and
            # sits flush with the bottom edge.
            "actions": (
                "sticky bottom-0 z-10 -mx-4 -mb-4 mt-4 border-t border-border "
                "bg-background/95 px-4 py-3 backdrop-blur"
            ),
            # Matched to "body"'s max-w-xl so the buttons line up with
            # the record above them rather than drifting to the edges.
            #
            # flex-col-reverse below sm puts the primary group (last in
            # source order) on top and the destructive one at the
            # bottom, so Delete is never the button under your thumb
            # when the bar stacks. From sm up, source order is restored
            # and "actions-primary" pushes itself right.
            "actions-inner": (
                "mx-auto flex w-full max-w-xl flex-col-reverse gap-2 "
                "sm:flex-row sm:items-center"
            ),
            # The right-hand group. sm:ml-auto does the separating, so
            # the bar reads Delete-left / everything-else-right when a
            # Delete is present and simply right-aligns when it isn't
            # (create, and detail once Delete moved to the edit page).
            "actions-primary": "flex flex-col gap-2 sm:ml-auto sm:flex-row",
        },
    },
}


class UnknownUIVariant(KeyError):
    """Raised for an unknown component or modifier.

    A typo raises rather than resolving to an empty class string, so it
    surfaces in the adapter's own render tests instead of shipping an
    unstyled button.
    """


def _group(component: str, name: str) -> dict[str, str]:
    return UI_REGISTRY[component].get(name, {})  # type: ignore[return-value]


def ui(component: str, *modifiers: str) -> str:
    """Resolve a component's class string from :data:`UI_REGISTRY`.

    Registered as the ``ui`` Jinja global (see
    :class:`polyadmin.templating.Renderer`), so ``admin/*.html`` can call
    ``{{ ui("button", "outline", "size-sm") }}``.

    A modifier naming a part resolves to that part alone; modifiers
    naming a variant or size compose with the component's base, filling
    in "default"/"size-default" for whichever axis the caller left out.
    See the module docstring for why the two behave differently.
    """
    if component not in UI_REGISTRY:
        known = ", ".join(sorted(UI_REGISTRY))
        raise UnknownUIVariant(f"unknown ui component {component!r} (known: {known})")

    variants = _group(component, "variants")
    sizes = _group(component, "sizes")
    parts = _group(component, "parts")

    # A single part reference stands alone.
    if len(modifiers) == 1 and modifiers[0] in parts:
        return parts[modifiers[0]]

    base = UI_REGISTRY[component].get("base", "")
    resolved: list[str] = [base] if base else []

    has_size = any(m.startswith("size-") for m in modifiers)
    has_variant = any(not m.startswith("size-") for m in modifiers)
    if not has_variant and "default" in variants:
        resolved.append(variants["default"])
    if not has_size and "size-default" in sizes:
        resolved.append(sizes["size-default"])

    for modifier in modifiers:
        if modifier in variants:
            resolved.append(variants[modifier])
        elif modifier in sizes:
            resolved.append(sizes[modifier])
        elif modifier in parts:
            raise UnknownUIVariant(
                f"ui {component!r} part {modifier!r} cannot be combined with other "
                "modifiers (a part replaces the base; request it on its own)"
            )
        else:
            known = ", ".join(sorted({**variants, **sizes, **parts}))
            raise UnknownUIVariant(
                f"ui component {component!r} has no modifier {modifier!r} (known: {known})"
            )

    return " ".join(p for p in resolved if p)
