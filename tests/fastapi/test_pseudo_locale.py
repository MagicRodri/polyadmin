"""Render every page in the pseudo-locale and fail on visible English.

SWEEP_AREAS turns on one group of pages at a time, so each conversion
commit leaves the suite green.
"""

import re
from html.parser import HTMLParser

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard
from polyadmin.core.filter import BooleanFilter
from polyadmin.core.widget import (
    Activity,
    Chart,
    Metric,
    Progress,
    Stat,
    Table,
    Timeline,
)
from polyadmin.fastapi.router import create_router
from polyadmin.i18n import PSEUDO_LOCALE
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.fastapi.test_inlines import make_client as make_inline_client
from tests.fastapi.test_inlines import seed_org_with_users

SWEEP_AREAS = {"layout": True, "list": True, "forms": True, "detail": False, "errors": False}
LOCALE_NAMES = ["English", "Français", "Русский", "Pseudo (en-XA)"]
VISIBLE_ATTRS = {"placeholder", "aria-label", "title", "alt", "hx-confirm"}
PSEUDO = re.compile(r"\[[^\[\]]*\]")
LETTER = re.compile(r"[^\W\d_]")


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self._skip += 1
        self.runs += [value for name, value in attrs if name in VISIBLE_ATTRS and value]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.runs.append(data)


def untranslated(page, allow=()):
    parser = _Visible()
    parser.feed(page)
    out = []
    for run in parser.runs:
        text = run.strip()
        rest = text
        while (stripped := PSEUDO.sub("", rest)) != rest:
            rest = stripped
        for value in allow:
            rest = rest.replace(value, "")
        if LETTER.search(rest):
            out.append(text)
    return out


def test_untranslated_helper():
    page = """<html><head><title>[Üšérš] · [Àdmîñ]</title><script>var x = "Hello";</script></head>
<body x-data="{ open: a > b }"><p>[Šàvé]</p><p>Save</p><input placeholder="Search"><td>a@example.com</td>
<span>[Délété [Üšér]]</span><button aria-label="[Çlöšé]"></button></body></html>"""
    assert sorted(untranslated(page, ["a@example.com"])) == ["Save", "Search"]


def main_client(tmp_path):
    class FilteredUserAdmin(InMemoryUserAdmin):
        filters = [BooleanFilter("is_active")]

    users = FilteredUserAdmin()
    users.create({"email": "a@example.com", "is_active": True})
    users.create({"email": "b@example.com", "is_active": False})
    dashboard = Dashboard(
        title="Overview",
        widgets=[
            Metric("Users", value=2),
            Stat("Signups", value=7, delta=12.5),
            Progress("Onboarding", value=3, target=10),
            Table("Recent", columns=["email"], rows=[{"email": "a@example.com"}]),
            Chart("Growth", series=[("Mon", 5)]),
            Activity("Feed", entries=["user created"]),
            Timeline("History", entries=[("May", "Launch", "")]),
        ],
    )
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "hello.html").write_text(
        '{% extends "admin/base.html" %}{% block content %}<p>{{ _("Hello") }}</p>{% endblock %}'
    )

    async def hello(ctx):
        return ctx.render("pages/hello.html")

    admin = Admin(model_admins=[users], dashboard=dashboard, pseudo_locale=True)
    admin.route("/hello", hello, label="Hello")
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin", template_dirs=(tmp_path,)), prefix="/admin")
    allow = ["a@example.com", "b@example.com", "Mon", "user created", "Launch", "May", "PO", *LOCALE_NAMES]
    return TestClient(app), allow


def inline_client(tmp_path):
    client, org_admin, user_admin = make_inline_client(pseudo_locale=True)
    seed_org_with_users(org_admin, user_admin, "a@example.com")
    return client, ["a@example.com", "Acme", "PO", *LOCALE_NAMES]


PAGES = [
    ("layout", "shell", "/admin/hello", {}, main_client),
    ("list", "list", "/admin/users", {}, main_client),
    ("list", "list fragment", "/admin/users?search=a", {"HX-Request": "true"}, main_client),
    ("forms", "create", "/admin/users/create", {}, main_client),
    ("forms", "edit", "/admin/users/1/edit", {}, main_client),
    ("forms", "inline edit", "/admin/organizations/1/edit", {}, inline_client),
    ("detail", "detail", "/admin/users/1", {}, main_client),
    ("detail", "delete", "/admin/users/1/delete", {}, main_client),
    ("detail", "inline detail", "/admin/organizations/1", {}, inline_client),
    ("detail", "dashboard", "/admin", {}, main_client),
    ("errors", "not found", "/admin/users/999", {}, main_client),
]


@pytest.mark.parametrize(("area", "name", "path", "headers", "factory"), PAGES, ids=[f"{p[0]}/{p[1]}" for p in PAGES])
def test_pseudo_locale_sweep(tmp_path, area, name, path, headers, factory):
    if not SWEEP_AREAS[area]:
        pytest.skip(f"area {area!r} not converted yet")
    client, allow = factory(tmp_path)
    client.cookies.set("admin_locale", PSEUDO_LOCALE)
    response = client.get(path, headers=headers)
    assert response.status_code < 500
    left = untranslated(response.text, allow)
    assert not left, f"untranslated on {path}:\n  " + "\n  ".join(left)
