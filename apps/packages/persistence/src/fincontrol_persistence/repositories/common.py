"""SQLAlchemy repositories: helpers shared by several features.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from typing import Any

from fincontrol_core.domain.pagination import PageMeta, PaginationParams
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session


def apply_sort_and_paginate(
    session: Session,
    stmt: Select[Any],
    params: PaginationParams,
    allowed_sort_columns: dict[str, Any],
    default_column: Any,
    tie_breaker: Any,
) -> tuple[list[Any], PageMeta]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total_items = int(session.scalar(count_stmt) or 0)

    sort_col = allowed_sort_columns.get(params.sort_by, default_column)
    direction = desc if params.is_descending else asc
    # The primary key breaks ties so equal sort values never shuffle between pages (D-04).
    paginated_stmt = (
        stmt.order_by(direction(sort_col), direction(tie_breaker))
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = list(session.scalars(paginated_stmt).all())
    meta = PageMeta.build(params, total_items)
    return items, meta
