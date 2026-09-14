"""OrganizationAdmin: the relation target for UserAdmin.organization."""
from __future__ import annotations

from datetime import date

from models import Organization, OrganizationRepository

from polyadmin import DateField, DecimalField, ModelAdmin, StringField
from polyadmin.core.inline import TabularInline


def _valid_founded_date(value):
    """Rejects a Founded value the framework couldn't already coerce:
    Field.parse_form_value (polyadmin/core/field.py) does no date parsing
    of its own (unlike the "decimal" field type), so any non-empty string
    reaching here has to be checked by hand.
    """
    if not isinstance(value, str) or value == "":
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("Enter a valid date.") from None


def _valid_balance(value):
    """Rejects a Balance value parse_form_value could not parse: it hands
    back the raw string unchanged when float() fails, a float otherwise,
    so seeing a non-empty string here means the input was bad.
    """
    if isinstance(value, str) and value != "":
        raise ValueError("Enter a valid number.")


class OrganizationAdmin(ModelAdmin):
    model = Organization

    category = "Directory"

    list_display = ["id", "name", "founded", "balance"]
    form_fields = ["name", "founded", "balance"]
    search_fields = ["name"]
    fields = [
        StringField("name", required=True),
        DateField("founded", validators=[_valid_founded_date]),
        DecimalField("balance", validators=[_valid_balance]),
    ]
    # Shows each Organization's Users inline on its own
    # create/detail/edit pages -- see docs/inlines.md.
    inlines = [TabularInline("users", "organization")]

    def __init__(self, repository: OrganizationRepository) -> None:
        super().__init__()
        self.repository = repository

    def get_queryset(self):
        return self.repository.list()

    def get_object(self, pk):
        try:
            return self.repository.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        return self.repository.create(
            name=data["name"],
            founded=_parse_founded(data.get("founded")),
            balance=_parse_balance(data.get("balance")),
        )

    def update(self, obj, data):
        return self.repository.update(
            obj,
            name=data["name"],
            founded=_parse_founded(data.get("founded")),
            balance=_parse_balance(data.get("balance")),
        )


def _parse_founded(value):
    """Founded arrives as the raw YYYY-MM-DD string once _valid_founded_date
    has already rejected anything malformed (create()/update() only run
    once ModelAdmin.validate has passed) -- absent/empty is None.
    """
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_balance(value):
    """Balance arrives as a float once Field.parse_form_value has already
    coerced it (and _valid_balance has rejected anything it couldn't) --
    absent/empty is None, saved as 0.0. No further conversion needed: the
    model's `balance` is itself a plain float (see models.py), and
    templating.py's decimal_display already renders a float as fixed-point,
    shortest round-trip digits -- manufacturing a Decimal here (previously
    via Decimal(str(value)), to dodge float's binary imprecision) would
    only add an unnecessary type change with no display benefit.
    """
    return value if value is not None else 0.0
