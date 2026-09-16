"""delete_selected's confirmation step when the ModelAdmin previews deletes
(docs/deletes.md)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from polyadmin.core.delete import (
    DELETE_PREVIEW_SAMPLE,
    resolve_delete_preview,
    selection_fingerprint,
)
from polyadmin.core.template_context import _object_label
from polyadmin.fastapi.auth import compute_permissions

CONFIRMED_FIELD = "_confirmed"
FINGERPRINT_FIELD = "_fingerprint"
RETURN_FIELD = "_return"


def confirm_delete_selected(
    request: Request,
    form: Any,
    admin: Any,
    model_admin: Any,
    renderer: Any,
    principal: Any,
    objects: list[Any],
    select_all: bool,
    return_to: str,
    list_request: Any,
    base_path: str,
) -> HTMLResponse | None:
    """Answer with the confirmation page (deleting nothing), or return None when
    the confirmed, unchanged, unblocked selection may be deleted."""
    fingerprint = selection_fingerprint(model_admin, objects)
    confirmed = bool(form.get(CONFIRMED_FIELD))
    changed = confirmed and select_all and form.get(FINGERPRINT_FIELD) != fingerprint
    preview = resolve_delete_preview(admin, model_admin, principal, objects)
    if confirmed and not changed and not preview.blocked:
        return None
    slug = model_admin.get_slug()
    # Built here rather than in the context builder: the per-object view check
    # lives in the adapter, and core must not import one.
    items = [
        {
            "label": _object_label(model_admin, obj),
            "url": f"{base_path}/{slug}/{model_admin.get_pk(obj)}"
            if compute_permissions(admin, principal, model_admin, obj)["can_view"]
            else None,
        }
        for obj in objects[:DELETE_PREVIEW_SAMPLE]
    ]
    selection = {
        "objects": objects,
        "select_all": select_all,
        "pks": [] if select_all else [str(model_admin.get_pk(obj)) for obj in objects],
        "list_request": list_request,
        "fingerprint": fingerprint,
        "return_to": return_to,
        "changed": changed,
        "items": items,
    }
    html = renderer.render_delete_selected(
        admin,
        model_admin,
        selection,
        preview,
        base_path=base_path,
        principal=principal,
        csrf_token=request.state.csrf_token,
    )
    return HTMLResponse(html)
