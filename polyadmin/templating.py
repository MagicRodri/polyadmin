"""Renderer: turns a ModelAdmin plus data into an HTML page.

Templates resolve in three levels: an explicit override, then the application
directories in the order given, then this package's own. `render_list_fragment`
and `render_form_fragment` render the inner region alone for htmx swaps,
sharing the full page's TemplateContext builder so the two never drift apart.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import jinja2

from polyadmin.core.admin import Admin
from polyadmin.core.inline import INLINE_MULTISELECT_ROWS, Inline
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import Page
from polyadmin.core.query import DEFAULT_EMPTY_VALUE, ListRequest
from polyadmin.core.template_context import (
    dashboard_context,
    delete_context,
    detail_context,
    form_context,
    list_context,
)
from polyadmin.i18n import I18n, LocaleOption, get_locale, gettext
from polyadmin.ui import ui

# Imported lazily, not at module level: polyadmin.fastapi.__init__ imports
# router -> handlers -> Renderer, so an eager import here would close the
# cycle.

FRAMEWORK_TEMPLATES_DIR = Path(__file__).parent / "templates"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$")


def iso_date(value: Any) -> str | None:
    """YYYY-MM-DD, the only form the browser-side formatter reads for a date."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and _ISO_DATE.match(value):
        return value
    return None


def iso_datetime(value: Any) -> str | None:
    """ISO 8601 with its offset when aware; a naive value stays naive and is
    shown as wall-clock time.
    """
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, str) and _ISO_DATETIME.match(value):
        return value
    return None


def form_value(value: Any, field_type: str) -> str:
    """A field's value as its form control's value attribute.

    A date or datetime-local input discards anything but its own ISO form
    -- str() of an aware datetime carries an offset and a space -- so a
    date is written as YYYY-MM-DD and a datetime as YYYY-MM-DDTHH:MM, its
    wall-clock time, as the input shows it. None is empty; anything else
    (a string posted back after a validation error) is shown as given.
    """
    if value is None:
        return ""
    if field_type == "date" and isinstance(value, date):
        return (value.date() if isinstance(value, datetime) else value).isoformat()
    if field_type == "datetime" and isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    return str(value)


def decimal_display(value: Any) -> str:
    """Fixed-point text for a decimal value -- never the scientific notation
    plain str() can fall into (a Decimal built from scientific-notation
    input, or any sufficiently large/small float), which would throw off
    the browser-side formatter's fraction-digit count.

    A Decimal is shown exactly as the host gave it -- format(value, "f")
    only changes notation, never precision, so a host's Decimal("12.50")
    keeps its two places. A float carries no such intended precision (it
    is what Field.parse_form_value hands back for the "decimal" field
    type -- see core/field.py), so it is shown with the shortest digit
    string that round-trips back to the same float, in fixed-point, with
    no trailing ".0" -- the same contract as Go's decimalText
    (fiber/render_helpers.go), which uses strconv.FormatFloat(f, 'f', -1,
    64). Anything else (an int) falls back to plain str().
    """
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return _shortest_fixed_point(value)
    return str(value)


def _shortest_fixed_point(value: float) -> str:
    """The shortest decimal string that round-trips back to `value`, in
    fixed-point notation, with no forced trailing zero.

    repr(value) is Python's own shortest round-tripping form, but it can
    be scientific notation for a large/small magnitude (repr(1e21) ==
    "1e+21"); routing it through Decimal expands that to fixed-point
    without losing or adding digits. What Decimal's own "f" format does
    add back is a trailing ".0" for a whole number (Decimal("1E+2") formats
    as "100", but Decimal("100.0") -- what repr(100.0) produces -- formats
    as "100.0"), so a fractional part of all zeros is stripped afterwards.
    """
    text = format(Decimal(repr(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


@dataclass(frozen=True)
class LocaleSwitcher:
    """The language switcher's data; None when it is off."""

    options: list[LocaleOption]
    current: str


class Renderer:
    def __init__(
        self,
        *,
        template_dirs: Iterable[str | Path] = (),
        i18n: I18n | None = None,
        switcher_enabled: bool = False,
    ) -> None:
        self.switcher_enabled = switcher_enabled
        self.i18n = i18n or I18n.from_admin(Admin())
        search_dirs = [str(d) for d in template_dirs] + [str(FRAMEWORK_TEMPLATES_DIR)]
        loader = jinja2.FileSystemLoader(search_dirs)
        # One environment per locale: the i18n extension installs gettext
        # per environment, and the request's locale picks one (see `env`).
        self._envs = {locale: self._make_env(loader, locale) for locale in self.i18n.supported}

    def _make_env(self, loader: jinja2.BaseLoader, locale: str) -> jinja2.Environment:
        env = jinja2.Environment(
            loader=loader,
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=["jinja2.ext.i18n"],
        )
        translator = self.i18n.translator

        # Our own callables, not Jinja's newstyle wrappers: those mark a
        # translation as Markup, which let a host string through `_()`
        # unescaped, and always %-format, which broke on a label containing
        # "%". These return plain text, so autoescape escapes it at output
        # and `|tojson` sees the raw string. `_()` formats only when given
        # arguments -- a literal % needs %% only then, as with Go's t.
        def translate(message: str, **variables: Any) -> str:
            text = str(translator.gettext(locale, message))
            return text % variables if variables else text

        def translate_plural(singular: str, plural: str, num: int, **variables: Any) -> str:
            variables.setdefault("num", num)
            return str(translator.ngettext(locale, singular, plural, num)) % variables

        # newstyle=False installs them as they are. `_` is the extension's
        # alias for `gettext`; pgettext/npgettext are left unset (no template
        # uses them), as is `{% trans %}`, which nothing uses either.
        env.install_gettext_callables(translate, translate_plural, newstyle=False)
        # A global rather than a per-template import, so overrides and
        # custom page/widget templates style with the same vocabulary for
        # free.
        env.globals["ui"] = ui
        # The macro default in components/field.html.
        env.globals["DEFAULT_EMPTY_VALUE"] = DEFAULT_EMPTY_VALUE
        # How many options a tabular inline's listbox shows before it
        # scrolls. Four keeps the row near the height of the controls
        # beside it.
        env.globals["INLINE_MULTISELECT_ROWS"] = INLINE_MULTISELECT_ROWS
        env.globals["locale"] = locale
        env.globals["locale_switcher"] = self._switcher(locale)
        env.filters["iso_date"] = iso_date
        env.filters["iso_datetime"] = iso_datetime
        env.filters["decimal_display"] = decimal_display
        env.filters["form_value"] = form_value
        return env

    def _switcher(self, locale: str) -> LocaleSwitcher | None:
        # Set by create_router from Admin.locale_switcher; a bare Renderer
        # (tests) shows none.
        if not self.switcher_enabled or len(self.i18n.supported) < 2:
            return None
        return LocaleSwitcher(options=self.i18n.options(), current=locale)

    @property
    def env(self) -> jinja2.Environment:
        """The environment for the current request's locale."""
        return self._envs.get(get_locale()) or self._envs[self.i18n.default]

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.env.get_template(template_name).render(**context)

    def render_candidates(self, candidates: Sequence[str], context: dict[str, Any]) -> str:
        return self.env.select_template(candidates).render(**context)

    def render_list(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        page: Page,
        *,
        list_request: ListRequest | None = None,
        permissions: dict[str, bool] | None = None,
        relation_permissions: dict[str, bool] | None = None,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
        principal: Any = None,
        csrf_token: str = "",
    ) -> str:
        context = list_context(
            admin,
            model_admin,
            page,
            list_request=list_request,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            messages=messages,
            principal=principal,
            csrf_token=csrf_token,
        )
        return self.render_candidates(model_admin.get_template_candidates("list"), context)

    def render_list_fragment(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        page: Page,
        *,
        list_request: ListRequest | None = None,
        permissions: dict[str, bool] | None = None,
        relation_permissions: dict[str, bool] | None = None,
        base_path: str = "/admin",
        principal: Any = None,
        csrf_token: str = "",
    ) -> str:
        context = list_context(
            admin,
            model_admin,
            page,
            list_request=list_request,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            principal=principal,
            csrf_token=csrf_token,
        )
        return self.render("admin/components/list_content.html", context)

    def render_detail(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        obj: Any,
        *,
        principal: Any = None,
        csrf_token: str = "",
        permissions: dict[str, bool] | None = None,
        relation_permissions: dict[str, bool] | None = None,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        from polyadmin.fastapi.inlines import build_inline_context

        context = detail_context(
            admin,
            model_admin,
            obj,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            messages=messages,
            principal=principal,
            csrf_token=csrf_token,
        )
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, "readonly", base_path)
        context["wide_body"] = _wide_body(context["inlines"])
        context["history"] = _history_for(admin, model_admin, obj)
        return self.render_candidates(model_admin.get_template_candidates("detail"), context)

    def render_form(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        *,
        principal: Any = None,
        csrf_token: str = "",
        obj: Any | None = None,
        data: dict[str, Any] | None = None,
        errors: dict[str, list[str]] | None = None,
        non_field_errors: list[str] | None = None,
        relation_options: dict[str, list[tuple[Any, Any]]] | None = None,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        from polyadmin.fastapi.auth import compute_permissions
        from polyadmin.fastapi.inlines import build_inline_context

        context = form_context(
            admin,
            model_admin,
            obj=obj,
            data=data,
            errors=errors,
            non_field_errors=non_field_errors,
            relation_options=relation_options,
            permissions=compute_permissions(admin, principal, model_admin, obj),
            base_path=base_path,
            messages=messages,
            principal=principal,
            csrf_token=csrf_token,
        )
        mode = "placeholder" if obj is None else "edit"
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, mode, base_path)
        context["wide_body"] = _wide_body(context["inlines"])
        return self.render_candidates(model_admin.get_template_candidates("form"), context)

    def render_form_fragment(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        *,
        principal: Any = None,
        csrf_token: str = "",
        obj: Any | None = None,
        data: dict[str, Any] | None = None,
        errors: dict[str, list[str]] | None = None,
        non_field_errors: list[str] | None = None,
        relation_options: dict[str, list[tuple[Any, Any]]] | None = None,
        base_path: str = "/admin",
    ) -> str:
        from polyadmin.fastapi.auth import compute_permissions
        from polyadmin.fastapi.inlines import build_inline_context

        context = form_context(
            admin,
            model_admin,
            obj=obj,
            data=data,
            errors=errors,
            non_field_errors=non_field_errors,
            relation_options=relation_options,
            permissions=compute_permissions(admin, principal, model_admin, obj),
            base_path=base_path,
            principal=principal,
            csrf_token=csrf_token,
        )
        mode = "placeholder" if obj is None else "edit"
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, mode, base_path)
        return self.render("admin/components/form_wrapper.html", context)

    def render_inline_fragment(
        self,
        admin: Admin,
        principal: Any,
        model_admin: ModelAdmin,
        obj: Any,
        inline: Inline,
        *,
        base_path: str = "/admin",
        redisplay: dict[str, Any] | None = None,
    ) -> str:
        """Renders one inline section standalone: the response body for the inline
        create/update/delete routes, swapped into `#inline-{child_slug}` by
        htmx.
        """
        from polyadmin.fastapi.inlines import build_inline_context

        sections = build_inline_context(admin, principal, model_admin, obj, "edit", base_path, redisplay=redisplay)
        section = next(s for s in sections if s["slug"] == inline.child)
        return self.render("admin/components/inline_fragment.html", {"admin": admin, "base_path": base_path, "inline": section})

    def render_dashboard(
        self,
        admin: Admin,
        dashboard: Any,
        widgets: list[Any],
        *,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
        principal: Any = None,
        csrf_token: str = "",
    ) -> str:
        context = dashboard_context(admin, dashboard, widgets, base_path=base_path, messages=messages, principal=principal, csrf_token=csrf_token)
        return self.render("admin/dashboard.html", context)

    def render_login(
        self,
        admin: Admin,
        *,
        csrf_token: str = "",
        identifier: str = "",
        error: str = "",
        notice: str = "",
        base_path: str = "",
    ) -> str:
        """The login page. Deliberately not built on base_context: there is no
        principal (that is the point), no nav, and no trail to sit in.
        """
        return self.render(
            "admin/login.html",
            {
                "csrf_token": csrf_token,
                "site_title": admin.site_title,
                "site_logo_url": admin.site_logo_url,
                "identifier": identifier,
                "error": error,
                "notice": notice,
                "base_path": base_path,
            },
        )

    def render_lookup(self, options: list[tuple[Any, Any]]) -> str:
        return self.render("admin/components/lookup_results.html", {"options": options})

    def render_delete(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        obj: Any,
        *,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
        principal: Any = None,
        csrf_token: str = "",
    ) -> str:
        context = delete_context(admin, model_admin, obj, base_path=base_path, messages=messages, principal=principal, csrf_token=csrf_token)
        return self.render_candidates(model_admin.get_template_candidates("delete"), context)


# A summary of recent activity, not an audit browser: a logger wanting the
# full trail exposed can surface it where it already lives.
HISTORY_LIMIT = 10


def _wide_body(inlines) -> bool:
    """Whether any inline section is tabular. A table needs more than the max-w-xl
    a column of form fields wants -- squeezing one in is what clipped its row
    actions -- so such a page gets ui("page", "body-wide").
    """
    return any(inline.get("layout") == "tabular" for inline in inlines or [])


def _audit_action(action: str) -> str:
    """How the History panel names what happened. The framework's own verbs are
    translated; anything else is the name of the Action that ran, an
    identifier stored in the log, and stays as it is.
    """
    from polyadmin.core.audit import AUDIT_CREATE, AUDIT_DELETE, AUDIT_UPDATE

    verbs = {AUDIT_CREATE: gettext("create"), AUDIT_UPDATE: gettext("update"), AUDIT_DELETE: gettext("delete")}
    return verbs.get(action, action)


def _history_for(admin: Any, model_admin: Any, obj: Any) -> list[dict[str, str]]:
    """The record's recent audit entries, or [] when no logger is configured or
    the one configured cannot read back. Built in the request's locale:
    "system" and the framework's verbs are translated here; who did it, and
    when, are data.
    """
    from polyadmin.core.audit import AuditReader

    reader = admin.audit_logger
    if reader is None or not isinstance(reader, AuditReader):
        return []
    try:
        entries = reader.history(model_admin.get_slug(), model_admin.get_pk(obj), HISTORY_LIMIT)
    except Exception as exc:  # noqa: BLE001
        # A history panel is not worth failing a page render over.
        logging.getLogger("polyadmin").warning(
            "audit history unavailable for %s: %s", model_admin.get_slug(), exc
        )
        return []
    rendered = []
    system = gettext("system")
    for entry in entries:
        who = system
        principal = entry.principal
        if principal is not None:
            who = getattr(principal, "display_name", None) or str(
                getattr(principal, "id", "") or system
            )
        rendered.append(
            {"when": entry.at.strftime("%Y-%m-%d %H:%M"), "who": who, "what": _audit_action(entry.action)}
        )
    return rendered
