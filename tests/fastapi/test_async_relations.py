"""A ModelAdmin with async hooks and a list_page works as a relation target
and as an inline child -- the paths that used to call hooks synchronously."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import ForeignKeyField, ManyToManyField, StringField
from polyadmin.core.filter import RelationFilter
from polyadmin.core.inline import TabularInline
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf


class Org:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Member:
    def __init__(self, id, email, organization=None):
        self.id = id
        self.email = email
        self.organization = organization
        self.teams = []


class AsyncOrgAdmin(ModelAdmin):
    model = Org
    slug = "orgs"
    list_display = ["id", "name"]
    form_fields = ["name"]
    search_fields = ["name"]
    fields = [StringField("name", required=True)]
    inlines = [TabularInline("members", "organization")]

    def __init__(self):
        super().__init__()
        self.store: dict[int, Org] = {}

    async def list_page(self, list_request):
        rows = list(self.store.values())
        if list_request.search:
            rows = [o for o in rows if list_request.search.lower() in o.name.lower()]
        return rows, len(rows)

    async def get_object(self, pk):
        return self.store.get(int(pk))

    async def create(self, data):
        obj = Org(max(self.store, default=0) + 1, data["name"])
        self.store[obj.id] = obj
        return obj


class AsyncMemberAdmin(ModelAdmin):
    model = Member
    slug = "members"
    list_display = ["id", "email", "organization"]
    form_fields = ["email", "organization", "teams"]
    fields = [
        StringField("email", required=True),
        ForeignKeyField("organization", relation=Relation("organization", target="orgs", display_field="name")),
        ManyToManyField("teams", relation=Relation("teams", target="orgs", display_field="name", cardinality="many")),
    ]

    def __init__(self, orgs):
        super().__init__()
        self.orgs = orgs
        self.store: dict[int, Member] = {}
        self.seen_filters: list[dict[str, str]] = []

    async def list_page(self, list_request):
        self.seen_filters.append(dict(list_request.filters))
        wanted = list_request.filters.get("organization")
        rows = [
            m
            for m in self.store.values()
            if wanted is None or (m.organization is not None and str(m.organization.id) == wanted)
        ]
        return rows, len(rows)

    async def get_object(self, pk):
        return self.store.get(int(pk))

    async def create(self, data):
        org = await self.orgs.get_object(data["organization"]) if data.get("organization") else None
        member = Member(max(self.store, default=0) + 1, data["email"], org)
        self.store[member.id] = member
        return member

    async def update(self, obj, data):
        obj.email = data.get("email", obj.email)
        if data.get("organization"):
            obj.organization = await self.orgs.get_object(data["organization"])
        return obj

    async def delete(self, obj):
        del self.store[obj.id]


class FilteredMemberAdmin(AsyncMemberAdmin):
    filters = [RelationFilter("organization")]


class AutocompleteFilteredMemberAdmin(FilteredMemberAdmin):
    autocomplete_fields = ["organization"]


def make_client(member_cls=AsyncMemberAdmin):
    orgs = AsyncOrgAdmin()
    members = member_cls(orgs)
    admin = Admin(model_admins=[orgs, members])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), orgs, members


def seed(orgs, members):
    acme = orgs.store[1] = Org(1, "Acme")
    other = orgs.store[2] = Org(2, "Other Ltd")
    members.store[1] = Member(1, "a@example.com", acme)
    members.store[2] = Member(2, "b@example.com", other)
    return acme, other


# --- as a relation target -------------------------------------------------


def test_an_async_target_fills_a_foreign_key_select_and_a_many_to_many_list():
    client, orgs, members = make_client()
    seed(orgs, members)

    page = client.get("/admin/members/create").text

    assert "Acme" in page
    assert "Other Ltd" in page


def test_an_async_target_fills_the_select_on_a_failed_create_post():
    client, orgs, members = make_client()
    seed(orgs, members)

    response = client.post("/admin/members/create", data={"email": ""}, headers=csrf(client))

    assert response.status_code == 422
    assert "Acme" in response.text


def test_an_async_target_fills_the_select_on_the_edit_page():
    client, orgs, members = make_client()
    seed(orgs, members)

    page = client.get("/admin/members/1/edit").text

    assert "Acme" in page
    assert "Other Ltd" in page


# --- as a relation filter target -------------------------------------------


def test_an_async_target_supplies_relation_filter_choices():
    client, orgs, _ = make_client(FilteredMemberAdmin)
    orgs.store[1] = Org(1, "Acme")

    page = client.get("/admin/members").text

    # No member row mentions the organization, so this is the filter's choice.
    assert "Acme" in page


def test_an_async_target_labels_the_relation_filter_combobox():
    client, orgs, _ = make_client(AutocompleteFilteredMemberAdmin)
    orgs.store[1] = Org(1, "Acme")

    page = client.get("/admin/members", params={"filter[organization]": "1"}).text

    assert "Acme" in page


# --- as an inline child ---------------------------------------------------


def test_an_async_child_renders_as_an_inline_on_the_edit_page():
    client, orgs, members = make_client()
    seed(orgs, members)

    page = client.get("/admin/orgs/1/edit").text

    assert 'id="inline-members"' in page
    assert "a@example.com" in page
    assert "b@example.com" not in page


def test_an_async_child_renders_as_a_readonly_inline_on_the_detail_page():
    client, orgs, members = make_client()
    seed(orgs, members)

    page = client.get("/admin/orgs/1").text

    assert 'id="inline-members"' in page
    assert "a@example.com" in page
    assert "b@example.com" not in page


def test_a_list_page_child_is_asked_for_the_parents_rows():
    client, orgs, members = make_client()
    seed(orgs, members)

    client.get("/admin/orgs/1/edit")

    assert members.seen_filters == [{"organization": "1"}]


def test_the_create_page_does_not_query_the_child():
    client, _, members = make_client()

    response = client.get("/admin/orgs/create")

    assert response.status_code == 200
    assert "Save to add Members." in response.text
    assert members.seen_filters == []


def test_an_async_child_can_be_added_edited_and_removed_inline():
    client, orgs, members = make_client()
    seed(orgs, members)

    created = client.post("/admin/orgs/1/inlines/members", data={"email": "new@example.com"}, headers=csrf(client))
    assert created.status_code == 200
    assert "new@example.com" in created.text
    new_pk = max(members.store)
    assert members.store[new_pk].organization is orgs.store[1]

    updated = client.post(
        f"/admin/orgs/1/inlines/members/{new_pk}", data={"email": "changed@example.com"}, headers=csrf(client)
    )
    assert updated.status_code == 200
    assert members.store[new_pk].email == "changed@example.com"

    removed = client.request("DELETE", f"/admin/orgs/1/inlines/members/{new_pk}", headers=csrf(client))
    assert removed.status_code == 200
    assert new_pk not in members.store
    assert "changed@example.com" not in removed.text


def test_an_async_child_redisplays_a_failed_inline_add():
    client, orgs, members = make_client()
    seed(orgs, members)

    response = client.post("/admin/orgs/1/inlines/members", data={"email": ""}, headers=csrf(client))

    assert response.status_code == 422
    assert 'id="inline-members"' in response.text
