from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal
from polyadmin.core.authorization import SuperuserAuthorizer
from polyadmin.fastapi.router import create_router

BROADCAST_TEMPLATE = """
{% extends "admin/base.html" %}
{% block content %}
<h1>{{ page.label }}</h1>
<form method="post">
  <input name="message" value="{{ message | default('') }}">
  <button type="submit">Send</button>
</form>
{% endblock %}
"""


async def broadcast_page(ctx):
    if ctx.request.method == "POST":
        form = await ctx.form()
        return ctx.redirect(
            f"{ctx.base_path}/tools/broadcast", flash=("success", f"Broadcast sent: {form.get('message')}")
        )
    return ctx.render("pages/broadcast.html")


def make_client(tmp_path, *, authenticator=None, authorizer=None, **route_kwargs):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "broadcast.html").write_text(BROADCAST_TEMPLATE)

    admin = Admin(authenticator=authenticator, authorizer=authorizer)
    admin.route("/tools/broadcast", broadcast_page, label="Broadcast Message", **route_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin", template_dirs=(tmp_path,)), prefix="/admin")
    return TestClient(app)


def test_get_renders_page_template_inside_shared_layout(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/admin/tools/broadcast")
    assert response.status_code == 200
    assert "Broadcast Message" in response.text
    # shared layout: sidebar/breadcrumb chrome from base.html is present
    assert "Dashboard" in response.text


def test_post_reposts_and_redirects_with_flash(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/admin/tools/broadcast", data={"message": "hello"})
    assert response.status_code == 200  # TestClient follows the 303 redirect by default
    assert "Broadcast sent: hello" in response.text


def test_unauthenticated_request_is_rejected(tmp_path):
    client = make_client(tmp_path, authenticator=DenyAllAuthenticator())
    assert client.get("/admin/tools/broadcast").status_code == 401


def test_authenticated_but_unauthorized_request_is_rejected(tmp_path):
    client = make_client(
        tmp_path,
        authenticator=AllowAllAuthenticator(Principal(id="u1", is_superuser=False)),
        authorizer=SuperuserAuthorizer(),
    )
    assert client.get("/admin/tools/broadcast").status_code == 403


def test_default_permission_derived_from_path_is_enforced(tmp_path):
    class OnlyReportsPermission:
        def can(self, principal, permission, resource=None):
            return permission != "page.tools.broadcast"

    client = make_client(tmp_path, authenticator=AllowAllAuthenticator(), authorizer=OnlyReportsPermission())
    assert client.get("/admin/tools/broadcast").status_code == 403


def test_explicit_permission_overrides_default(tmp_path):
    class CustomPermission:
        def can(self, principal, permission, resource=None):
            return permission == "custom.broadcast"

    client = make_client(
        tmp_path,
        authenticator=AllowAllAuthenticator(),
        authorizer=CustomPermission(),
        permission="custom.broadcast",
    )
    assert client.get("/admin/tools/broadcast").status_code == 200
