"""Static asset mounting for the FastAPI adapter."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

import polyadmin

FRAMEWORK_STATIC_DIR = Path(polyadmin.__file__).resolve().parent / "static"


def mount_static(router: APIRouter, *, static_dir: str | Path | None = None) -> None:
    """Mount the admin's static assets at `<base_path>/static/*`.

    Pass `static_dir` to serve an application's own directory (for
    `custom.css`/`custom.js`) instead of the framework's.
    """
    directory = Path(static_dir) if static_dir else FRAMEWORK_STATIC_DIR
    if not directory.exists():
        return
    router.mount("/static", StaticFiles(directory=str(directory)), name="admin-static")
