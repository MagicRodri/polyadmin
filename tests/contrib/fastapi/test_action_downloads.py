from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin import Download
from polyadmin.core.action import action
from polyadmin.core.admin import Admin
from polyadmin.core.field import StringField
from polyadmin.contrib.fastapi.responses import content_disposition
from polyadmin.contrib.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class DownloadUserAdmin(InMemoryUserAdmin):
    @action(label="Emails")
    def emails(self, objects, principal):
        return Download("emails.csv", "text/csv", content="\n".join(o.email for o in objects).encode())

    @action(label="Streamed")
    async def streamed(self, objects, principal):
        async def chunks():
            for obj in objects:
                yield (obj.email + "\n").encode()

        return Download("сотрудники.txt", "text/plain", stream=chunks())

    @action(label="With form", form=[StringField("sep", required=True)])
    def with_form(self, objects, principal, data):
        return Download("joined.txt", "text/plain", content=data["sep"].join(o.email for o in objects).encode())


def make_client():
    users = DownloadUserAdmin()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    return TestClient(app), users


def post(client, name, data):
    return client.post(f"/admin/users/actions/{name}", data=data, follow_redirects=False, headers=csrf(client))


def test_download_action_answers_with_the_file():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    b = users.create({"email": "b@x.com"})
    response = post(client, "emails", {"pks": [str(a.id), str(b.id)]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="emails.csv"')
    assert response.content == b"a@x.com\nb@x.com"


def test_streamed_download_with_non_ascii_name():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "streamed", {"pks": [str(a.id)]})
    assert response.status_code == 200
    assert (
        "filename*=UTF-8''%D1%81%D0%BE%D1%82%D1%80%D1%83%D0%B4%D0%BD%D0%B8%D0%BA%D0%B8.txt"
        in response.headers["content-disposition"]
    )
    assert response.content == b"a@x.com\n"


def test_form_action_can_answer_with_a_download():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    b = users.create({"email": "b@x.com"})
    response = post(client, "with_form", {"pks": [str(a.id), str(b.id)], "_confirmed": "1", "sep": ";"})
    assert response.content == b"a@x.com;b@x.com"


def test_content_disposition_strips_quotes_from_the_fallback():
    assert content_disposition('a"b.csv').startswith('attachment; filename="ab.csv"')
    assert content_disposition("файл.csv").startswith('attachment; filename=".csv"')
