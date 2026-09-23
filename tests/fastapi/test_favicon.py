from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def make_client(user_admin, **admin_kwargs):
    admin = Admin(model_admins=[user_admin], **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_model_admins_own_favicon_wins_over_the_site_wide():
    class FaviconUserAdmin(InMemoryUserAdmin):
        favicon_url = "https://example.com/user.ico"

    client = make_client(FaviconUserAdmin(), site_favicon_url="https://example.com/site.ico")
    page = client.get("/admin/users").text
    assert '<link rel="icon" href="https://example.com/user.ico">' in page, page
    assert "site.ico" not in page, "the site-wide favicon leaked in alongside the model admin's own"


def test_favicon_falls_back_to_the_site_wide_when_unset():
    client = make_client(InMemoryUserAdmin(), site_favicon_url="https://example.com/site.ico")
    page = client.get("/admin/users").text
    assert '<link rel="icon" href="https://example.com/site.ico">' in page, page


def test_no_favicon_tag_when_neither_is_set():
    client = make_client(InMemoryUserAdmin())
    page = client.get("/admin/users").text
    assert 'rel="icon"' not in page, page
