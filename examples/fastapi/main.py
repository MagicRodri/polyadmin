"""Reference FastAPI application exercising the PolyAdmin package.

Run with:

    uv run uvicorn main:app --reload

then open http://127.0.0.1:8000/admin
"""

import os

from fastapi import FastAPI
from models import OrganizationRepository, RoleRepository, UserRepository, seed
from organization_admin import OrganizationAdmin
from pages import register_pages
from project_admin import ClientAdmin, ProjectAdmin
from role_admin import RoleAdmin
from session import CookieSessionBackend, ReadOnlyForNonSuperusers
from sql_models import open_projects_database
from user_admin import UserAdmin

from polyadmin.core.admin import Admin
from polyadmin import Download
from polyadmin.core.dashboard import Dashboard, DashboardExport, DateRangeFilter, SelectFilter
from polyadmin.core.widget import (
    Chart,
    Column,
    DataTable,
    Donut,
    Metric,
    MetricGroup,
    Rows,
    Stat,
    Table,
    Tabs,
    Tile,
    Timeline,
    WidgetUnavailable,
)
from polyadmin.contrib.fastapi.router import create_router

users = UserRepository()
organizations = OrganizationRepository()
roles = RoleRepository()
seed(users, organizations, roles)
projects_db = open_projects_database()

def _users_in(ctx):
    selected = ctx.filters["organization"]
    return [u for u in users.list() if not selected or (u.organization and str(u.organization.id) == selected)]


def overview_tiles(ctx):
    scoped = _users_in(ctx)
    active = sum(1 for u in scoped if u.is_active)
    return [
        Tile("Users", len(scoped), icon="users", hint=f"active: {active}"),
        Tile("Organizations", len(organizations.list()), icon="file-text"),
        Tile("Roles", len(roles.list()), icon="activity"),
        Tile("Inactive users", len(scoped) - active, icon="user"),
    ]


def organization_rows(ctx):
    items = []
    for org in organizations.list():
        members = [u for u in users.list() if u.organization is org]
        active = sum(1 for u in members if u.is_active)
        share = {"count": active, "percentage": active / len(members) * 100 if members else 0}
        items.append({"name": org.name, "users": len(members), "active": share})
    total_users = sum(i["users"] for i in items)
    total_active = sum(i["active"]["count"] for i in items)
    totals = {"name": "All", "users": total_users,
              "active": {"count": total_active, "percentage": total_active / total_users * 100 if total_users else 0}}
    return Rows(items, total=len(items), totals=totals)


def user_rows(ctx):
    scoped = [u for u in _users_in(ctx) if not ctx.search or ctx.search in u.email]
    page = scoped[ctx.offset : ctx.offset + ctx.limit]
    return Rows(
        [{"email": u.email, "organization": u.organization.name if u.organization else None, "active": "yes" if u.is_active else "no"} for u in page],
        total=len(scoped),
    )


def billing(ctx):
    raise WidgetUnavailable("The billing service is not configured in this demo.")


def export_users(ctx):
    lines = ["email", *(u.email for u in _users_in(ctx))]
    return Download("users.csv", "text/csv", content="\n".join(lines).encode())


dashboard = Dashboard(
    title="Overview",
    filters=[
        DateRangeFilter("period", label="Period"),
        SelectFilter("organization", label="Organization", empty_label="All organizations", searchable=True,
                     get_choices=lambda: [(o.id, o.name) for o in organizations.list()]),
    ],
    exports=[DashboardExport("users-csv", label="Export users", handler=export_users)],
    widgets=[
        MetricGroup("At a glance", key="overview", placement="top", depends_on=["organization"], get_tiles=overview_tiles),
        DataTable(
            "Organizations", key="organizations", size="lg", depends_on=[], page_size=None,
            columns=[Column("name", "Organization", strong=True), Column("users", "Users", align="end", format="number"),
                     Column("active", "Active", align="end", format="share")],
            get_rows=organization_rows,
        ),
        DataTable(
            "Users", key="users", size="full", depends_on=["organization"], page_size=25, searchable=True,
            search_placeholder="Search by email", total_label="{total} users",
            description=lambda ctx: f"{ctx.filters['period'].start:%Y-%m-%d} – {ctx.filters['period'].end:%Y-%m-%d}",
            columns=[Column("email", "Email", strong=True), Column("organization", "Organization", empty="none"),
                     Column("active", "Active")],
            get_rows=user_rows,
        ),
        MetricGroup("Billing", key="billing", depends_on=[], get_tiles=billing),
        Metric("Users", key="user-count", get_value=lambda: len(users.list())),
        Metric("Organizations", key="organization-count", get_value=lambda: len(organizations.list())),
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
    model_admins=[
        UserAdmin(users, organizations, roles),
        OrganizationAdmin(organizations, users),
        RoleAdmin(roles, users),
        ClientAdmin(session_factory=projects_db),
        ProjectAdmin(session_factory=projects_db),
    ],
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
    # amelie@example.com carries "fr" in Principal.extra (session.py);
    # everyone else resolves through the switcher cookie and
    # Accept-Language instead.
    locale_resolver=lambda request, p: (p.extra.get("locale") or None) if p else None,
    # en-XA, bracketed and accented, so a page can be swept for text that
    # never went through the translator -- see browsertests/test_i18n.py.
    pseudo_locale=os.environ.get("POLYADMIN_PSEUDO_LOCALE") == "1",
)
register_pages(admin, users)

app = FastAPI(title="Admin Example")
app.include_router(
    create_router(admin, base_path="/admin", template_dirs=["templates"]), prefix="/admin"
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"admin": "/admin"}
