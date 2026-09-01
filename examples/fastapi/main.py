"""Reference FastAPI application exercising the PolyAdmin package.

Run with:

    uv run uvicorn main:app --reload

then open http://127.0.0.1:8000/admin
"""

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard
from polyadmin.core.widget import Chart, Donut, Metric, Stat, Table, Tabs, Timeline
from polyadmin.fastapi.router import create_router
from fastapi import FastAPI
from models import OrganizationRepository, RoleRepository, UserRepository, seed
from organization_admin import OrganizationAdmin
from pages import register_pages
from role_admin import RoleAdmin
from session import CookieSessionBackend, ReadOnlyForNonSuperusers
from user_admin import UserAdmin

users = UserRepository()
organizations = OrganizationRepository()
roles = RoleRepository()
seed(users, organizations, roles)

dashboard = Dashboard(
    title="Overview",
    widgets=[
        Metric("Users", get_value=lambda: len(users.list())),
        Metric("Organizations", get_value=lambda: len(organizations.list())),
        Chart(
            "Users per organization",
            get_series=lambda: [
                (org.name, sum(1 for u in users.list() if u.organization is org))
                for org in organizations.list()
            ],
        ),
        # Stat pairs the number with its trend. A real app would get the
        # delta by comparing against a previous-period query; these demo
        # repositories keep no history, so it's a fixed stand-in here.
        Stat(
            "Active users",
            get_stat=lambda: (sum(1 for u in users.list() if u.is_active), 12.5),
        ),
        # Two breakdowns of the same population sharing one card. Each
        # panel is an ordinary widget; all of them render up front, so
        # switching tabs costs no round trip.
        Tabs(
            "User breakdown",
            panels=[
                (
                    "By status",
                    Donut(
                        "Users by status",
                        get_series=lambda: [
                            ("Active", sum(1 for u in users.list() if u.is_active)),
                            ("Inactive", sum(1 for u in users.list() if not u.is_active)),
                        ],
                    ),
                ),
                (
                    "By organization",
                    Donut(
                        "Users by organization",
                        get_series=lambda: [
                            (org.name, sum(1 for u in users.list() if u.organization is org))
                            for org in organizations.list()
                        ]
                        + [("Unassigned", sum(1 for u in users.list() if u.organization is None))],
                    ),
                ),
            ],
        ),
        Table(
            "Recent users",
            columns=["email", "organization"],
            get_rows=lambda: [
                {
                    "email": u.email,
                    "organization": u.organization.name if u.organization else "—",
                }
                for u in users.list()
            ],
        ),
        # Timeline is Activity's richer sibling: each entry carries its
        # own timestamp and body. A real app would order by a created_at
        # column and format the time however it likes -- the widget only
        # ever displays the string it's given.
        Timeline(
            "Latest activity",
            get_entries=lambda: [
                (f"user #{u.id}", "Account created", u.email)
                for u in sorted(users.list(), key=lambda u: u.id, reverse=True)[:3]
            ],
        ),
    ],
)

sessions = CookieSessionBackend()
admin = Admin(
    model_admins=[UserAdmin(users, organizations, roles), OrganizationAdmin(organizations), RoleAdmin(roles)],
    dashboard=dashboard,
    # Cookie sessions over an in-memory user table (session.py). One
    # object serves as both halves: login_backend is what mounts the
    # admin's login page and makes an unauthenticated request redirect to
    # it, and authenticator is what reads the session back on every
    # subsequent request.
    #
    # This replaced an AllowAllAuthenticator hardcoded to a superuser,
    # which meant nothing below -- SuperuserAuthorizer, per-object
    # permissions, the audit log's principal -- was ever exercised
    # against an identity anyone actually proved.
    authenticator=sessions,
    login_backend=sessions,
    # Not SuperuserAuthorizer: that would deny the viewer account every
    # permission, dashboard included. See session.py.
    authorizer=ReadOnlyForNonSuperusers(),
)
register_pages(admin, users)

app = FastAPI(title="Admin Example")
app.include_router(
    create_router(admin, base_path="/admin", template_dirs=["templates"]), prefix="/admin"
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"admin": "/admin"}
