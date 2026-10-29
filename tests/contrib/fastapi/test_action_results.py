import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin import ResultItem, ResultPage
from polyadmin.contrib.fastapi.router import create_router
from polyadmin.core.action import action
from polyadmin.core.admin import Admin
from polyadmin.core.field import StringField
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class ResultUserAdmin(InMemoryUserAdmin):
    @action(label="Issue token")
    def issue_token(self, objects, principal):
        return ResultPage(
            title="Token issued",
            message="Shown once.",
            items=[
                ResultItem("Email", objects[0].email),
                ResultItem("Token", "s3cret-<token>", copy=True),
            ],
        )

    @action(label="Centered")
    def centered(self, objects, principal):
        return ResultPage(title="Centered", align="center")

    @action(label="Tag", form=[StringField("tag", required=True)])
    def tag(self, objects, principal, data):
        return ResultPage(title="Tagged", items=[ResultItem("Tag", data["tag"])])


def make_client():
    users = ResultUserAdmin()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    return TestClient(app), users


def post(client, name, data):
    return client.post(f"/admin/users/actions/{name}", data=data, follow_redirects=False, headers=csrf(client))


def test_result_page_shows_its_items_once():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "issue_token", {"pks": [str(a.id)], "_return": f"/admin/users/{a.id}"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    html = response.text
    assert "Token issued" in html and "Shown once." in html
    assert "a@x.com" in html
    assert "s3cret-&lt;token&gt;" in html
    assert 'id="action-result-back"' in html and f'href="/admin/users/{a.id}"' in html
    assert "/actions/issue_token" not in html
    assert "admin_messages" not in response.headers.get("set-cookie", "")


def test_only_copyable_items_get_a_copy_button():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    html = post(client, "issue_token", {"pks": [str(a.id)]}).text
    assert html.count('x-ref="value"') == 1


def test_form_action_can_answer_with_a_result_page():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "tag", {"pks": [str(a.id)], "_confirmed": "1", "tag": "vip"})
    assert response.status_code == 200
    assert "Tagged" in response.text and "vip" in response.text


def result_class(html):
    start = html.index('id="action-result"')
    return html[start : html.index(">", start)]


def test_result_page_starts_aligned_unless_centered():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    assert "mx-auto" not in result_class(post(client, "issue_token", {"pks": [str(a.id)]}).text)
    assert "mx-auto" in result_class(post(client, "centered", {"pks": [str(a.id)]}).text)


def test_result_page_refuses_an_unknown_alignment():
    with pytest.raises(ValueError):
        ResultPage(title="x", align="left")
