"""ClientAdmin and ProjectAdmin: SQLAlchemy-backed resources, no repository
and no data-access hooks of their own."""

from __future__ import annotations

from sql_models import Client, Project

from polyadmin.contrib.sqlalchemy import SQLAlchemyModelAdmin
from polyadmin.core.field import EnumField, ForeignKeyField
from polyadmin.core.filter import BooleanFilter, ChoiceFilter, DateFilter, RelationFilter
from polyadmin.core.relation import Relation

STATUSES = [("planned", "Planned"), ("active", "Active"), ("done", "Done")]


class ClientAdmin(SQLAlchemyModelAdmin):
    model = Client
    category = "Projects"
    list_display = ("id", "name")
    form_fields = ("name",)
    search_fields = ("name",)


class ProjectAdmin(SQLAlchemyModelAdmin):
    model = Project
    category = "Projects"
    list_display = ("id", "name", "client", "status", "active", "due")
    form_fields = ("name", "client", "status", "active", "due")
    search_fields = ("name",)
    autocomplete_fields = ("client",)
    filters = (
        ChoiceFilter("status", choices=STATUSES),
        BooleanFilter("active"),
        RelationFilter("client"),
        DateFilter("due"),
    )
    default_filters = {"active": True}
    fields = (
        ForeignKeyField("client", relation=Relation("client", target="clients", display_field="name")),
        EnumField("status", choices=[value for value, _ in STATUSES], required=True),
    )
