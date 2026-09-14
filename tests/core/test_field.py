from datetime import date
from decimal import Decimal

from polyadmin.core.field import (
    BooleanField,
    DateField,
    DecimalField,
    EnumField,
    Field,
    StringField,
)


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


def test_date_field_parses_a_posted_string():
    field = DateField("founded")
    assert field.parse_form_value("2019-03-01") == date(2019, 3, 1)
    assert field.parse_form_value("") is None


def test_date_field_rejects_a_malformed_posted_string():
    field = DateField("founded")
    # parse_form_value hands back the unparsed string; validate() is what
    # turns that into a form error, rather than letting it through to
    # ModelAdmin.create()/update() as a value to be silently defaulted.
    assert field.parse_form_value("someday") == "someday"
    assert field.validate("someday") == ["Enter a valid date."]
    assert field.validate(date(2019, 3, 1)) == []
    assert field.validate(None) == []  # not required: absent is fine


def test_decimal_field_parses_a_posted_string():
    field = DecimalField("balance")
    assert field.parse_form_value("1234.50") == Decimal("1234.50")
    assert field.parse_form_value("") is None


def test_decimal_field_rejects_a_malformed_posted_string():
    field = DecimalField("balance")
    assert field.parse_form_value("twelve") == "twelve"
    assert field.validate("twelve") == ["Enter a valid number."]
    assert field.validate(Decimal("1234.5")) == []
    assert field.validate(None) == []
