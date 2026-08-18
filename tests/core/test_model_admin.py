import pytest

from polyadmin.core.field import BooleanField, StringField
from polyadmin.core.model_admin import ModelAdmin


class User:
    def __init__(self, id, email, is_active=True):
        self.id = id
        self.email = email
        self.is_active = is_active


class InMemoryUserAdmin(ModelAdmin):
    model = User

    list_display = ["id", "email", "is_active"]
    form_fields = ["email", "is_active"]
    search_fields = ["email"]
    fields = [
        BooleanField("is_active", default=True),
        StringField("email", required=True),
    ]

    def __init__(self):
        super().__init__()
        self._store: dict[int, User] = {}
        self._next_id = 1

    def get_queryset(self):
        return list(self._store.values())

    def get_object(self, pk):
        # pk arrives as a string from URL path params; coerce so lookups
        # by int (in-process) and by str (over HTTP) both work.
        try:
            return self._store.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        obj = User(id=self._next_id, **data)
        self._store[obj.id] = obj
        self._next_id += 1
        return obj

    def update(self, obj, data):
        for key, value in data.items():
            setattr(obj, key, value)
        return obj

    def delete(self, obj):
        del self._store[obj.id]


def test_slug_defaults_from_model_name():
    admin = InMemoryUserAdmin()
    assert admin.get_slug() == "users"


def test_slug_can_be_overridden():
    class CustomSlugAdmin(InMemoryUserAdmin):
        slug = "people"

    assert CustomSlugAdmin().get_slug() == "people"


def test_category_defaults_to_none():
    assert InMemoryUserAdmin().category is None


def test_category_can_be_declared():
    class GroupedUserAdmin(InMemoryUserAdmin):
        category = "Directory"

    assert GroupedUserAdmin().category == "Directory"


def test_model_is_required():
    class NoModelAdmin(ModelAdmin):
        pass

    with pytest.raises(TypeError):
        NoModelAdmin()


def test_fields_are_resolved_from_list_display_and_form_fields():
    admin = InMemoryUserAdmin()
    fields = admin.get_fields()
    assert set(fields) == {"id", "email", "is_active"}
    # explicitly declared field is used as-is, not overwritten by the implicit default
    assert fields["is_active"].default is True


def test_get_list_display_values():
    admin = InMemoryUserAdmin()
    user = admin.create({"email": "john@example.com", "is_active": False})
    assert admin.get_list_display_values(user) == {
        "id": 1,
        "email": "john@example.com",
        "is_active": False,
    }


def test_crud_lifecycle():
    admin = InMemoryUserAdmin()
    user = admin.create({"email": "john@example.com"})
    assert admin.get_object(user.id) is user
    assert admin.get_queryset() == [user]

    admin.update(user, {"email": "john2@example.com"})
    assert user.email == "john2@example.com"

    admin.delete(user)
    assert admin.get_queryset() == []


def test_unimplemented_crud_raises_by_default():
    class BareAdmin(ModelAdmin):
        model = User

    admin = BareAdmin()
    with pytest.raises(NotImplementedError):
        admin.get_queryset()
    with pytest.raises(NotImplementedError):
        admin.get_object(1)
    with pytest.raises(NotImplementedError):
        admin.create({})
    with pytest.raises(NotImplementedError):
        admin.update(User(1, "a@example.com"), {})
    with pytest.raises(NotImplementedError):
        admin.delete(User(1, "a@example.com"))


def test_validate_required_field():
    admin = InMemoryUserAdmin()
    errors = admin.validate({"email": ""})
    assert "email" in errors
