from polyadmin.core.field import StringField
from polyadmin.core.filter import BooleanFilter, ChoiceFilter
from polyadmin.core.model_admin import ModelAdmin
from tests.core.test_model_admin import InMemoryUserAdmin, User


def test_boolean_filter_true():
    admin = InMemoryUserAdmin()
    active = admin.create({"email": "a@example.com", "is_active": True})
    admin.create({"email": "b@example.com", "is_active": False})

    filt = BooleanFilter("is_active")
    result = filt.apply(admin.get_queryset(), "true", admin)
    assert result == [active]


def test_boolean_filter_empty_value_is_noop():
    admin = InMemoryUserAdmin()
    admin.create({"email": "a@example.com", "is_active": True})
    admin.create({"email": "b@example.com", "is_active": False})

    filt = BooleanFilter("is_active")
    assert filt.apply(admin.get_queryset(), "", admin) == admin.get_queryset()


def test_boolean_filter_choices():
    filt = BooleanFilter("is_active")
    assert filt.choices_with_labels() == [("", "All"), ("true", "Yes"), ("false", "No")]


class RoleUser:
    def __init__(self, role):
        self.role = role


class RoleAdmin(ModelAdmin):
    model = User
    fields = [StringField("role")]


def test_choice_filter():
    role_admin = RoleAdmin()
    objects = [RoleUser("admin"), RoleUser("member")]

    filt = ChoiceFilter("role", choices=["admin", "member"])
    result = filt.apply(objects, "admin", role_admin)

    assert len(result) == 1 and result[0].role == "admin"
    assert filt.choices_with_labels() == [("", "All"), ("admin", "admin"), ("member", "member")]
