"""Pydantic response DTOs of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class CvmDocumentDTO(BaseModel):
    """One IPE document of a followed company."""

    id: int
    protocol: str
    tickers: list[str] = Field(default_factory=list)
    company_name: str
    category: str
    doc_type: str = ""
    species: str = ""
    subject: str = ""
    reference_date: date | None = None
    delivery_date: date
    version: int = 1
    link: str = ""
    read: bool = False
    first_seen_at: datetime | None = None


class DisclosureFeedDTO(BaseModel):
    items: list[CvmDocumentDTO] = Field(default_factory=list)
    unread_count: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    # Companies in scope and the tickers without a CNPJ in the FCA map yet.
    companies: int = 0
    unmapped: list[str] = Field(default_factory=list)
    latest_delivery: date | None = None
    note: str | None = None


class MarkReadResultDTO(BaseModel):
    updated: int
