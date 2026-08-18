import pytest

from polyadmin.core.admin import Admin
from polyadmin.core.model_admin import ModelAdmin


class User:
    def __init__(self, id):
        self.id = id


class UserAdmin(ModelAdmin):
    model = User


class OtherUserAdmin(ModelAdmin):
    model = User
    slug = "users"  # collides with UserAdmin's default slug


async def _noop_handler(ctx):
    return None


def test_register_preserves_order():
    a, b = UserAdmin(), UserAdmin()
    b.slug = "more-users"
    admin = Admin(model_admins=[a, b])
    assert admin.model_admins == [a, b]


def test_register_rejects_duplicate_slug():
    admin = Admin(model_admins=[UserAdmin()])
    with pytest.raises(ValueError):
        admin.register(OtherUserAdmin())


def test_get_model_admin_by_slug():
    admin = Admin(model_admins=[UserAdmin()])
    assert admin.get_model_admin("users").model is User
    with pytest.raises(KeyError):
        admin.get_model_admin("missing")


def test_route_registers_page_and_returns_it():
    admin = Admin()
    page = admin.route("/reports/contracts", _noop_handler)
    assert admin.pages == [page]
    assert page.path == "/reports/contracts"


def test_route_rejects_duplicate_path():
    admin = Admin()
    admin.route("/reports/contracts", _noop_handler)
    with pytest.raises(ValueError):
        admin.route("/reports/contracts", _noop_handler)


def test_pages_preserves_registration_order():
    admin = Admin()
    first = admin.route("/a", _noop_handler)
    second = admin.route("/b", _noop_handler)
    assert admin.pages == [first, second]


def test_route_derives_label_and_permission_from_path():
    admin = Admin()
    page = admin.route("/reports/contracts", _noop_handler)
    assert page.label == "Contracts"
    assert page.permission == "page.reports.contracts"


def test_route_path_must_start_with_slash():
    admin = Admin()
    with pytest.raises(ValueError):
        admin.route("reports/contracts", _noop_handler)


def test_route_icon_defaults_to_collection():
    admin = Admin()
    page = admin.route("/reports/contracts", _noop_handler)
    assert page.icon == "collection"


def test_route_icon_can_be_overridden():
    admin = Admin()
    page = admin.route("/reports/contracts", _noop_handler, icon="chart")
    assert page.icon == "chart"
