from polyadmin.core.field import BooleanField, EnumField, Field, StringField


class Obj:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_get_value_reads_attribute():
    field = StringField("email")
    assert field.get_value(Obj(email="john@example.com")) == "john@example.com"


def test_get_value_falls_back_to_default():
    field = StringField("nickname", default="anon")
    assert field.get_value(Obj()) == "anon"


def test_get_value_missing_without_default_is_none():
    field = StringField("nickname")
    assert field.get_value(Obj()) is None


def test_label_defaults_from_name():
    field = Field("created_at")
    assert field.label == "Created At"


def test_required_validation():
    field = BooleanField("is_active", required=True)
    assert field.validate(None) == ["Is Active is required."]
    assert field.validate(True) == []


def test_custom_validator():
    def not_admin(value):
        if value == "admin":
            raise ValueError("Reserved username.")

    field = StringField("username", validators=[not_admin])
    assert field.validate("admin") == ["Reserved username."]
    assert field.validate("john") == []


def test_enum_field_choices():
    field = EnumField("role", choices=["admin", "member"])
    assert field.choices == ["admin", "member"]
