import html
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.contrib.fastapi.router import create_router
from tests.contrib.sqlalchemy.models import Author, AuthorAdmin, make_session_factory, seed


class ActiveOnlyAuthorAdmin(AuthorAdmin):
    default_filters = {"active": True}


@pytest.fixture
def client(tmp_path):
    factory = make_session_factory(tmp_path / "db.sqlite")
    seed(factory, Author(name="on-author", active=True), Author(name="off-author", active=False))
    admin = Admin(model_admins=[ActiveOnlyAuthorAdmin(factory)], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_the_all_link_of_a_defaulted_filter_shows_every_row(client):
    page = client.get("/admin/authors").text
    assert "on-author" in page and "off-author" not in page
    links = [html.unescape(href) for href in re.findall(r'href="([^"]*filter%5Bactive%5D=[^"]*)"', page)]
    all_links = [link for link in links if re.search(r"filter%5Bactive%5D=(&|$)", link)]
    assert all_links, links
    everything = client.get(all_links[0]).text
    assert "on-author" in everything and "off-author" in everything
