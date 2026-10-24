"""Standardized pagination, sorting, and filtering primitives for high-volume listings."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

ALLOWED_SORT_ORDERS = frozenset({"asc", "desc"})


@dataclass(frozen=True)
class PaginationParams:
    """Normalized query parameters for paginated, sorted, and filtered listings."""

    page: int = 1
    page_size: int = 10
    sort_by: str = "id"
    sort_order: str = "asc"
    search: str | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1 or self.page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        if self.sort_order.lower() not in ALLOWED_SORT_ORDERS:
            raise ValueError("sort_order must be 'asc' or 'desc'")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def is_descending(self) -> bool:
        return self.sort_order.lower() == "desc"


@dataclass(frozen=True)
class PageMeta:
    """Pagination metadata returned alongside every list endpoint."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_prev: bool
    has_next: bool
    sort_by: str
    sort_order: str

    @classmethod
    def build(cls, params: PaginationParams, total_items: int) -> PageMeta:
        total_pages = max(1, math.ceil(total_items / params.page_size)) if total_items > 0 else 1
        return cls(
            page=params.page,
            page_size=params.page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_prev=params.page > 1,
            has_next=params.page < total_pages,
            sort_by=params.sort_by,
            sort_order=params.sort_order.lower(),
        )


@dataclass(frozen=True)
class PaginatedResult[T]:
    """Generic envelope for paginated queries with optional aggregate summary."""

    items: list[T]
    meta: PageMeta
    summary: dict[str, Any] = field(default_factory=dict)
