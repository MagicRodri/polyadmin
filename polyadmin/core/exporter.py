"""Exporter: turns a ModelAdmin's list query result into a downloadable
file. The adapter feeds it the *same* filtered/ordered
result set `execute_list_query` produced for the list view, so an
export always represents exactly the dataset the user was looking at,
respecting the resource's configured columns (`list_display`).

CSV streams row-by-row all the way to the HTTP response and never
holds more than one row in memory. XLSX is written with openpyxl's
write-only mode, which avoids materializing a Python object per row
--but the zip container format has to be finalized before any bytes
go out, so unlike CSV it is buffered once, not chunked, to the client.
Large XLSX exports should stay reasonable in row count for that reason.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from typing import Any

from polyadmin.core.admin import Admin
from polyadmin.core.field import Field
from polyadmin.core.model_admin import ModelAdmin


def cell_value(admin: Admin, field: Field, obj: Any) -> Any:
    """A field's export-friendly value: relation fields resolve to
    their target's display label (or a comma-joined list of them for
    ManyToMany) rather than exporting a raw Python object.
    """
    value = field.get_value(obj)
    if field.field_type in ("foreignkey", "onetoone"):
        if value is None:
            return ""
        target_admin = admin.get_model_admin(field.relation.target)
        return target_admin.get_field(field.relation.display_field).get_value(value)
    if field.field_type == "manytomany":
        if not value:
            return ""
        target_admin = admin.get_model_admin(field.relation.target)
        display_field = target_admin.get_field(field.relation.display_field)
        return ", ".join(str(display_field.get_value(item)) for item in value)
    return value


class Exporter:
    format: str
    content_type: str

    def file_extension(self) -> str:
        raise NotImplementedError

    def stream(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        objects: Iterable[Any],
        columns: list[str],
    ) -> Iterator[bytes]:
        raise NotImplementedError


class CSVExporter(Exporter):
    format = "csv"
    content_type = "text/csv"

    def file_extension(self) -> str:
        return "csv"

    def stream(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        objects: Iterable[Any],
        columns: list[str],
    ) -> Iterator[bytes]:
        fields = [model_admin.get_field(name) for name in columns]
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        writer.writerow([field.label for field in fields])
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)

        for obj in objects:
            writer.writerow([cell_value(admin, field, obj) for field in fields])
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)


class XLSXExporter(Exporter):
    format = "xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def file_extension(self) -> str:
        return "xlsx"

    def stream(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        objects: Iterable[Any],
        columns: list[str],
    ) -> Iterator[bytes]:
        from openpyxl import Workbook

        fields = [model_admin.get_field(name) for name in columns]
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet(model_admin.get_verbose_name())

        sheet.append([field.label for field in fields])
        for obj in objects:
            row = [cell_value(admin, field, obj) for field in fields]
            # openpyxl only accepts str/int/float/bool/datetime cells --
            # coerce anything else (None, UUID, dict/list from a JSON
            # field, ...) to a plain string.
            sheet.append(
                [
                    ""
                    if value is None
                    else value
                    if isinstance(value, (str, int, float, bool))
                    else str(value)
                    for value in row
                ]
            )

        buffer = io.BytesIO()
        workbook.save(buffer)
        yield buffer.getvalue()
