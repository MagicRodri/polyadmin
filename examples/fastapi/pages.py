"""A custom admin page -- demonstrates admin.route() for functionality
that isn't resource CRUD (a department-facing wizard, a report, an
internal tool). See docs/routing.md.
"""
from __future__ import annotations

from models import UserRepository


def register_pages(admin, users: UserRepository) -> None:
    async def broadcast(ctx):
        if ctx.request.method == "POST":
            form = await ctx.form()
            message = (form.get("message") or "").strip()
            if not message:
                return ctx.render("pages/broadcast.html", error="Message can't be empty.")
            recipients = sum(1 for u in users.list() if u.is_active)
            return ctx.redirect(
                f"{ctx.base_path}/tools/broadcast",
                flash=("success", f"Broadcast sent to {recipients} active user(s)."),
            )
        return ctx.render("pages/broadcast.html")

    admin.route(
        "/tools/broadcast",
        broadcast,
        label="Broadcast Message",
        category="Tools",
    )
