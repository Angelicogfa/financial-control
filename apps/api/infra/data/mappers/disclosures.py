"""Mapping between the CVM disclosure ORM models and the pure domain entities."""

from __future__ import annotations

from domain.disclosures.entities import CvmDocument, IssuerTicker
from infra.data.models.disclosures import CvmDocumentModel, CvmIssuerTickerModel


def to_issuer_ticker(model: CvmIssuerTickerModel) -> IssuerTicker:
    return IssuerTicker(
        ticker=model.ticker,
        cnpj=model.cnpj,
        company_name=model.company_name,
        reference_date=model.reference_date,
    )


def to_cvm_document(model: CvmDocumentModel) -> CvmDocument:
    return CvmDocument(
        protocol=model.protocol,
        cnpj=model.cnpj,
        company_name=model.company_name,
        category=model.category,
        delivery_date=model.delivery_date,
        cvm_code=model.cvm_code,
        doc_type=model.doc_type,
        species=model.species,
        subject=model.subject,
        reference_date=model.reference_date,
        version=model.version,
        link=model.link,
        first_seen_at=model.first_seen_at,
        read_at=model.read_at,
        id=model.id,
    )


def apply_cvm_document(model: CvmDocumentModel, doc: CvmDocument) -> CvmDocumentModel:
    """Copy the filed fields (never the read mark nor when it was first seen)."""
    model.protocol = doc.protocol
    model.version = doc.version
    model.cnpj = doc.cnpj
    model.company_name = doc.company_name[:200]
    model.cvm_code = doc.cvm_code[:16]
    model.category = doc.category[:120]
    model.doc_type = doc.doc_type[:120]
    model.species = doc.species[:120]
    model.subject = doc.subject
    model.reference_date = doc.reference_date
    model.delivery_date = doc.delivery_date
    model.link = doc.link
    return model
