from polyadmin.core.admin import Admin
from polyadmin.core.exporter import CSVExporter, XLSXExporter, cell_value
from polyadmin.core.field import ForeignKeyField, ManyToManyField, StringField
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation
from tests.core.test_model_admin import InMemoryUserAdmin


def make_admin_with_users(*emails):
    user_admin = InMemoryUserAdmin()
    for email in emails:
        user_admin.create({"email": email})
    admin = Admin(model_admins=[user_admin])
    return admin, user_admin


def test_csv_exporter_header_and_rows():
    admin, user_admin = make_admin_with_users("john@example.com", "mary@example.com")
    exporter = CSVExporter()

    chunks = list(exporter.stream(admin, user_admin, user_admin.get_queryset(), user_admin.list_display))
    csv_text = b"".join(chunks).decode("utf-8")

    lines = csv_text.strip().splitlines()
    assert lines[0] == "Id,Email,Is Active"
    assert "john@example.com" in lines[1]
    assert "mary@example.com" in lines[2]


def test_csv_exporter_streams_one_row_at_a_time():
    admin, user_admin = make_admin_with_users("a@example.com", "b@example.com", "c@example.com")
    exporter = CSVExporter()

    chunks = list(exporter.stream(admin, user_admin, user_admin.get_queryset(), user_admin.list_display))
    # header + 3 rows = 4 chunks, each yielded separately
    assert len(chunks) == 4


def test_csv_exporter_respects_column_subset():
    admin, user_admin = make_admin_with_users("john@example.com")
    exporter = CSVExporter()

    chunks = list(exporter.stream(admin, user_admin, user_admin.get_queryset(), ["email"]))
    csv_text = b"".join(chunks).decode("utf-8")
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Email"
    assert lines[1] == "john@example.com"


class Tag:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Organization:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Item:
    def __init__(self, id, organization=None, tags=None):
        self.id = id
        self.organization = organization
        self.tags = tags or []


class OrganizationAdmin(ModelAdmin):
    model = Organization
    slug = "organizations"
    fields = [StringField("name")]

    def get_queryset(self):
        return []


class TagAdmin(ModelAdmin):
    model = Tag
    slug = "tags"
    fields = [StringField("name")]

    def get_queryset(self):
        return []


def test_cell_value_resolves_foreign_key_to_display_label():
    org_admin = OrganizationAdmin()
    admin = Admin(model_admins=[org_admin])
    relation = Relation("organization", target="organizations", display_field="name")
    field = ForeignKeyField("organization", relation=relation)

    org = Organization(1, "Acme")
    assert cell_value(admin, field, Item(1, organization=org)) == "Acme"


def test_cell_value_foreign_key_none_is_empty_string():
    org_admin = OrganizationAdmin()
    admin = Admin(model_admins=[org_admin])
    relation = Relation("organization", target="organizations", display_field="name")
    field = ForeignKeyField("organization", relation=relation)

    assert cell_value(admin, field, Item(1)) == ""


def test_cell_value_many_to_many_joins_display_labels():
    tag_admin = TagAdmin()
    admin = Admin(model_admins=[tag_admin])
    relation = Relation("tags", target="tags", display_field="name", cardinality="many")
    field = ManyToManyField("tags", relation=relation)

    tags = [Tag(1, "urgent"), Tag(2, "billing")]
    assert cell_value(admin, field, Item(1, tags=tags)) == "urgent, billing"


def test_xlsx_exporter_produces_a_valid_workbook():
    import openpyxl

    admin, user_admin = make_admin_with_users("john@example.com")
    exporter = XLSXExporter()

    chunks = list(exporter.stream(admin, user_admin, user_admin.get_queryset(), user_admin.list_display))
    data = b"".join(chunks)

    import io

    workbook = openpyxl.load_workbook(io.BytesIO(data))
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ("Id", "Email", "Is Active")
    assert rows[1][1] == "john@example.com"
