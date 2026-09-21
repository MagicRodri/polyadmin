from polyadmin.core.field import (
    BooleanField,
    EnumField,
    Field,
    ForeignKeyField,
    ManyToManyField,
    StringField,
)
from polyadmin.core.relation import Relation


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


def test_foreign_key_reads_the_attribute_by_default():
    org = Obj(id=1)
    field = ForeignKeyField("organization", relation=Relation("organization", target="orgs"))
    assert field.get_value(Obj(organization=org)) is org


def test_foreign_key_uses_get_related_when_the_relation_has_one():
    # An id-based row holds organization_id, not an organization object: the
    # relation says how to build the related object from what the row has.
    field = ForeignKeyField(
        "organization",
        relation=Relation("organization", target="orgs", get_related=lambda row: Obj(id=row.organization_id)),
    )
    related = field.get_value(Obj(organization_id=7))
    assert related.id == 7


def test_many_to_many_uses_get_related_and_defaults_to_empty():
    field = ManyToManyField(
        "teams",
        relation=Relation("teams", target="orgs", cardinality="many", get_related=lambda row: [Obj(id=i) for i in row.team_ids]),
    )
    assert [t.id for t in field.get_value(Obj(team_ids=[1, 2]))] == [1, 2]
    assert ManyToManyField("teams", relation=Relation("teams", target="orgs", cardinality="many")).get_value(Obj()) == []
