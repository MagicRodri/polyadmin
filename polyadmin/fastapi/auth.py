"""Authentication + authorization wiring for the FastAPI adapter.

If `Admin` wasn't given an authenticator/authorizer, these are no-ops
-- every request is treated as authenticated and permitted, matching
the framework's behavior before Phase 5 existed.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.model_admin import ModelAdmin


def authorize(admin: Admin, request: Request, permission: str, resource: Any = None) -> tuple[Any, Response | None]:
    """Returns (principal, None) if the request may proceed, or
    (None, error_response) if it was rejected.
    """
    principal = None
    if admin.authenticator is not None:
        principal = admin.authenticator.authenticate(request)
        if principal is None:
            return None, HTMLResponse("Authentication required.", status_code=401)

    if admin.authorizer is not None and not admin.authorizer.can(principal, permission, resource):
        return None, HTMLResponse("Permission denied.", status_code=403)

    return principal, None


def compute_permissions(admin: Admin, principal: Any, model_admin: ModelAdmin) -> dict[str, bool]:
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
        return admin.authorizer.can(principal, resource_permission(slug, action), model_admin)

    # Keys are "can_view" etc -- see default_permissions in
    # template_context.py for why "update" alone is unsafe here.
    return {
        "can_view": allowed(model_admin.can_view, "view"),
        "can_create": allowed(model_admin.can_create, "create"),
        "can_update": allowed(model_admin.can_update, "update"),
        "can_delete": allowed(model_admin.can_delete, "delete"),
        "can_export": allowed(model_admin.can_export, "export"),
    }
