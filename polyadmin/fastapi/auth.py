"""Authentication + authorization wiring for the FastAPI adapter.

If `Admin` wasn't given an authenticator/authorizer, these are no-ops
-- every request is treated as authenticated and permitted, matching
the framework's behavior before Phase 5 existed.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.login import LOGIN_PATH, NEXT_QUERY_PARAM
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.fastapi.responses import redirect


def authorize(
    admin: Admin, request: Request, base_path: str, permission: str, resource: Any = None
) -> tuple[Any, Response | None]:
    """Returns (principal, None) if the request may proceed, or
    (None, error_response) if it was rejected.

    The unauthenticated case has two answers, and which one is right
    depends entirely on whether the admin has a login page to offer.
    With a login_backend configured, a browser is redirected there,
    carrying where it was going; without one there is nowhere to send
    anybody and 401 is the whole story. This is the only behavioural
    change login_backend makes to existing routes.

    Forbidden never redirects: the visitor is signed in and simply may
    not do this, so bouncing them to a login form would invite them to
    re-authenticate as the same person to the same refusal.
    """
    principal = None
    if admin.authenticator is not None:
        principal = admin.authenticator.authenticate(request)
        if principal is None:
            if admin.login_backend is None:
                return None, HTMLResponse("Authentication required.", status_code=401)
            # redirect(), not a bare 303: an expired session most often
            # shows up mid-page on an htmx request, where a 303 would be
            # swapped into the page as content. redirect() sends
            # HX-Redirect for those, navigating the whole window.
            return None, redirect(request, login_url(base_path, _requested_url(request)))

    if admin.authorizer is not None and not admin.authorizer.can(principal, permission, resource):
        return None, HTMLResponse("Permission denied.", status_code=403)

    return principal, None


def login_url(base_path: str, next_url: str = "") -> str:
    """The path an unauthenticated visitor is sent to, carrying where
    they were headed so signing in resumes it."""
    target = f"{base_path}{LOGIN_PATH}"
    if not next_url:
        return target
    return f"{target}?{NEXT_QUERY_PARAM}={quote(next_url, safe='')}"


def _requested_url(request: Request) -> str:
    """The path (with query) the current request was for -- what a
    redirect to login should come back to."""
    target = request.url.path
    if request.url.query:
        target += f"?{request.url.query}"
    return target


def authorize_object(admin: Admin, principal: Any, permission: str, obj: Any) -> bool:
    """Re-run a permission check with the loaded record as the resource,
    so an Authorizer can answer "may this principal touch *this* record"
    and not only "may they touch this model at all".

    It is the second, narrower gate: the coarse check has already run
    (before the record was fetched, so an unauthorized principal never
    costs a lookup), and this one runs once there is an object to judge.
    With no authorizer configured it permits, like every other check
    here.
    """
    if admin.authorizer is None:
        return True
    return admin.authorizer.can(principal, permission, obj)


def compute_permissions(
    admin: Admin, principal: Any, model_admin: ModelAdmin, obj: Any = None
) -> dict[str, bool]:
    """What the current principal may do with this resource, combining
    the ModelAdmin's static can_* capability toggles with the
    Authorizer's per-request decision. Used to decide
    which controls the templates show -- the routes enforce this
    independently, so hiding a control here is a UX nicety, not the
    security boundary.
    """
    slug = model_admin.get_slug()

    def allowed(capability: bool, action: str) -> bool:
        if not capability:
            return False
        if admin.authorizer is None:
            return True
        # obj is the record in view, or None on a list/create page. When
        # present it is what the authorizer is asked about, so per-object
        # rules decide which controls a record's own pages show.
        resource = model_admin if obj is None else obj
        return admin.authorizer.can(principal, resource_permission(slug, action), resource)

    # Keys are "can_view" etc -- see default_permissions in
    # template_context.py for why "update" alone is unsafe here.
    return {
        "can_view": allowed(model_admin.can_view, "view"),
        "can_create": allowed(model_admin.can_create, "create"),
        "can_update": allowed(model_admin.can_update, "update"),
        "can_delete": allowed(model_admin.can_delete, "delete"),
        "can_export": allowed(model_admin.can_export, "export"),
    }
