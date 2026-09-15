"""Authentication and authorization wiring for the FastAPI adapter. With no
authenticator or authorizer configured, these are no-ops: every request is
treated as authenticated and permitted.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.login import LOGIN_PATH, NEXT_QUERY_PARAM
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.fastapi.errors import forbidden, unauthenticated
from polyadmin.fastapi.locale import acached_principal
from polyadmin.fastapi.responses import redirect


async def authorize(
    admin: Admin, request: Request, base_path: str, permission: str, resource: Any = None
) -> tuple[Any, Response | None]:
    """Returns (principal, None) if the request may proceed, or (None,
    error_response) if it was rejected.

    Which answer the unauthenticated case gets depends on whether there is a
    login page to offer: with a login_backend the browser is redirected there
    carrying where it was going, without one 401 is the whole story. Forbidden
    never redirects -- the visitor is signed in and simply may not do this, so
    a login form would invite them to re-authenticate as the same person to the
    same refusal.
    """
    principal = None
    if admin.authenticator is not None:
        principal = await acached_principal(admin, request)
        if principal is None:
            if admin.login_backend is None:
                return None, unauthenticated(request, admin, base_path)
            # redirect(), not a bare 303: an expired session usually
            # surfaces mid-page on an htmx request, where a 303 would be
            # swapped in as content.
            return None, redirect(request, login_url(base_path, _requested_url(request)))

    if admin.authorizer is not None and not admin.authorizer.can(principal, permission, resource):
        return None, forbidden(request, admin, base_path)

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
    """Re-run a permission check with the loaded record as the resource, so an
    Authorizer can answer "may this principal touch this record" and not only
    "this model at all".

    The narrower of two gates: the coarse check already ran before the record
    was fetched, so an unauthorized principal never costs a lookup.
    """
    if admin.authorizer is None:
        return True
    return admin.authorizer.can(principal, permission, obj)


def compute_permissions(
    admin: Admin, principal: Any, model_admin: ModelAdmin, obj: Any = None
) -> dict[str, bool]:
    """What the principal may do with this resource, combining the ModelAdmin's
    static can_* toggles with the Authorizer's per-request decision. It decides
    which controls the templates show; the routes enforce this independently,
    so hiding a control is a UX nicety, not the security boundary.
    """
    slug = model_admin.get_slug()

    def allowed(capability: bool, action: str) -> bool:
        if not capability:
            return False
        if admin.authorizer is None:
            return True
        # obj is the record in view, or None on a list or create page.
        # When present it is what the authorizer is asked about, so per-
        # object rules decide which controls that record's pages show.
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
