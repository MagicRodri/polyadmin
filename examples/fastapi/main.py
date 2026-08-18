"""Reference FastAPI application exercising the PolyAdmin package.

Run with:

    uv run uvicorn main:app --reload

then open http://127.0.0.1:8000/admin
"""

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, Principal
from polyadmin.core.authorization import SuperuserAuthorizer
from polyadmin.core.dashboard import Dashboard
from polyadmin.core.widget import Chart, Donut, Metric, Stat, Table, Tabs, Timeline
from polyadmin.fastapi.router import create_router
from fastapi import FastAPI
from models import OrganizationRepository, UserRepository, seed
from organization_admin import OrganizationAdmin
from pages import register_pages
from user_admin import UserAdmin

users = UserRepository()
organizations = OrganizationRepository()
seed(users, organizations)

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

# Stand-ins for a real app's own session/IAM integration:
# swap these for something that reads your actual auth state.
admin = Admin(
    model_admins=[UserAdmin(users, organizations), OrganizationAdmin(organizations)],
    dashboard=dashboard,
    authenticator=AllowAllAuthenticator(
        Principal(id="demo", display_name="Demo Admin", is_superuser=True)
    ),
    authorizer=SuperuserAuthorizer(),
)
register_pages(admin, users)

app = FastAPI(title="Admin Example")
app.include_router(
    create_router(admin, base_path="/admin", template_dirs=["templates"]), prefix="/admin"
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"admin": "/admin"}
