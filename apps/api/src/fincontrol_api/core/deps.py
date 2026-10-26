"""Cross-cutting HTTP dependencies shared by every module router."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Query
from fincontrol_core.domain.pagination import PaginationParams
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

UoWFactory = Callable[[], AbstractUnitOfWork]


def pagination_query(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str = Query(default="id"),
    sort_order: str = Query(default="asc"),
    sort_dir: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PaginationParams:
    """Parse standardized pagination, sorting, and search query parameters."""
    order = (sort_dir or sort_order).lower()
    return PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=order,
        search=search,
    )
