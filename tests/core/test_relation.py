from polyadmin.core.field import ForeignKeyField, ManyToManyField, OneToOneField
from polyadmin.core.relation import Relation


class Organization:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class User:
    def __init__(self, id, organization=None, groups=None):
        self.id = id
        self.organization = organization
        self.groups = groups


def test_relation_get_value_defaults_to_getattr():
    relation = Relation("organization", target="organizations")
    org = Organization(1, "Acme")
    assert relation.get_value(User(1, organization=org)) is org


def test_relation_get_value_uses_custom_getter():
    relation = Relation("organization", target="organizations", get_related=lambda obj: "custom")
    assert relation.get_value(User(1)) == "custom"


def test_foreign_key_field_get_value_returns_related_object():
    relation = Relation("organization", target="organizations", display_field="name")
    field = ForeignKeyField("organization", relation=relation)
    org = Organization(1, "Acme")
    assert field.get_value(User(1, organization=org)) is org


def test_foreign_key_field_get_value_none_when_unset():
    relation = Relation("organization", target="organizations")
    field = ForeignKeyField("organization", relation=relation)
    assert field.get_value(User(1)) is None


def test_one_to_one_field_is_a_foreign_key_variant():
    relation = Relation("organization", target="organizations")
    field = OneToOneField("organization", relation=relation)
    assert field.field_type == "onetoone"
    assert isinstance(field, ForeignKeyField)


def test_many_to_many_field_defaults_to_empty_list():
    relation = Relation("groups", target="groups", cardinality="many")
    field = ManyToManyField("groups", relation=relation)
    assert field.get_value(User(1)) == []


def test_many_to_many_field_returns_related_objects():
    relation = Relation("groups", target="groups", cardinality="many")
    field = ManyToManyField("groups", relation=relation)
    groups = [Organization(1, "A"), Organization(2, "B")]
    assert field.get_value(User(1, groups=groups)) == groups
