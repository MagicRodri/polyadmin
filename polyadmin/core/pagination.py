"""In-memory pagination for the list view.

This paginates an already-materialized sequence. Once the query
pipeline lands, ORM/repository integrations will typically
paginate at the query level instead and only use `Page` as the result
shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass
class Page:
    items: list[Any]
    number: int
    page_size: int
    total_count: int

    @property
    def num_pages(self) -> int:
        if self.page_size <= 0 or self.total_count <= 0:
            return 1
        return -(-self.total_count // self.page_size)  # ceil division

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.num_pages

    @property
    def previous_page(self) -> int | None:
        return self.number - 1 if self.has_previous else None

    @property
    def next_page(self) -> int | None:
        return self.number + 1 if self.has_next else None


def paginate(items: Sequence[Any], *, page: int = 1, page_size: int = 25) -> Page:
    page = max(page, 1)
    page_size = max(page_size, 1)
    total_count = len(items)
    start = (page - 1) * page_size
    return Page(
        items=list(items[start : start + page_size]),
        number=page,
        page_size=page_size,
        total_count=total_count,
    )
