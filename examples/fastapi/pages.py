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
            # The RadioGroup/Switch/Slider on the page post like any
            # other form control -- each is a native input underneath (or,
            # for the Switch, a hidden input Alpine writes to), so there's
            # no JSON body or client-side state to unpack here.
            urgency = form.get("urgency") or "normal"
            channels = "in-app + email" if form.get("also_email") == "true" else "in-app"
            rate = form.get("rate") or "100"
            return ctx.redirect(
                f"{ctx.base_path}/tools/broadcast",
                flash=(
                    "success",
                    f"Broadcast sent to {recipients} active user(s) "
                    f"({urgency} urgency, {channels}, {rate}/min).",
                ),
            )
        return ctx.render("pages/broadcast.html")

    admin.route(
        "/tools/broadcast",
        broadcast,
        label="Broadcast Message",
        category="Tools",
    )
