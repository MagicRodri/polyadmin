"""The dashboard's page, its per-widget fragments and its exports
(docs/dashboard.md)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse

from polyadmin.core._async import maybe_await
from polyadmin.core.action import Download
from polyadmin.core.authorization import DASHBOARD_VIEW
from polyadmin.core.widget import DataTable, WidgetUnavailable, resolve_widget_data
from polyadmin.core.template_context import _describe, dashboard_card
from polyadmin.contrib.fastapi.auth import authorize
from polyadmin.contrib.fastapi.errors import forbidden, not_found
from polyadmin.contrib.fastapi.responses import clear_flash, download_response, pop_flash
from polyadmin.i18n import gettext

logger = logging.getLogger("polyadmin")

async def filters_view(dashboard: Any, dc: Any) -> list[dict[str, Any]]:
    views = []
    for f in dashboard.filters:
        value = dc.filters[f.name]
        if f.kind == "date_range":
            views.append(
                {"kind": f.kind, "name": f.name, "label": f.label, "from_param": f.from_param,
                 "to_param": f.to_param, "start": value.start.isoformat(), "end": value.end.isoformat()}
            )
        elif f.kind == "select":
            empty = gettext(f.empty_label) if f.empty_label else gettext("All")
            try:
                choices = await f.resolve_choices()
            except Exception:
                logger.exception("dashboard filter %r could not load its choices", f.name)
                choices = []
            views.append(
                {"kind": f.kind, "name": f.name, "label": f.label, "value": value or "",
                 "options": [("", empty), *choices], "placeholder": empty, "searchable": f.searchable}
            )
    return views


def build_dashboard_handlers(admin: Any, renderer: Any, base_path: str):
    async def index(request: Request):
        principal, error = await authorize(admin, request, base_path, DASHBOARD_VIEW)
        if error:
            return error
        dashboard = admin.dashboard
        widgets = dashboard.get_widgets(principal, admin.authorizer)
        dc = dashboard.context(request.query_params, principal)
        html = renderer.render_dashboard(
            admin,
            dashboard,
            widgets,
            cards=[dashboard_card(w, dashboard=dashboard, dc=dc, base_path=base_path) for w in widgets],
            filters_view=await filters_view(dashboard, dc),
            exports=dashboard.get_exports(principal, admin.authorizer),
            base_path=base_path,
            messages=pop_flash(request),
            principal=principal,
            csrf_token=request.state.csrf_token,
        )
        response = HTMLResponse(html)
        clear_flash(response)
        return response

    async def widget_view(request: Request, key: str):
        principal, error = await authorize(admin, request, base_path, DASHBOARD_VIEW)
        if error:
            return error
        dashboard = admin.dashboard
        widget = next((w for w in dashboard.get_widgets(principal, admin.authorizer) if w.key == key), None)
        if widget is None:
            return not_found(request, admin, base_path)
        ctx = dashboard.widget_context(widget, request.query_params, principal)
        data = state = message = None
        try:
            data = await resolve_widget_data(widget, ctx)
        except WidgetUnavailable as exc:
            state, message = "unavailable", exc.message
        except Exception:
            logger.exception("dashboard widget %r failed", widget.key)
            state = "unavailable"
        next_url = None
        if isinstance(data, dict) and data.get("next_offset") is not None:
            params = dashboard.query_params(ctx.filters)
            if ctx.search:
                params["search"] = ctx.search
            params["offset"] = str(data["next_offset"])
            next_url = f"{base_path}/_widgets/{widget.key}?{urlencode(params)}"
        html = renderer.render_widget_fragment(
            widget,
            widget_data=data,
            state=state,
            message=message,
            next_url=next_url,
            rows_only=isinstance(widget, DataTable) and ctx.offset > 0,
            description=_describe(widget, ctx),
        )
        return HTMLResponse(html)

    async def export_view(request: Request, name: str):
        principal, error = await authorize(admin, request, base_path, DASHBOARD_VIEW)
        if error:
            return error
        dashboard = admin.dashboard
        export = next((e for e in dashboard.exports if e.name == name), None)
        if export is None:
            return not_found(request, admin, base_path)
        if admin.authorizer is not None and not admin.authorizer.can(principal, export.permission, export):
            return forbidden(request, admin, base_path)
        result = await maybe_await(export.handler(dashboard.context(request.query_params, principal)))
        if not isinstance(result, Download):
            raise TypeError(f"Dashboard export {name!r} must return a Download, not {type(result).__name__}.")
        return download_response(result)

    return index, widget_view, export_view
