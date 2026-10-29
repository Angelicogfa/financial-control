"""SQLAlchemy repositories of the CVM disclosures (Phase 28).

They take and return pure domain entities and never commit (the Unit of Work does).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from domain.disclosures.entities import CvmDocument, IssuerTicker
from domain.disclosures.repositories import (
    AbstractCvmDocumentRepository,
    AbstractIssuerTickerRepository,
)
from infra.data.mappers.disclosures import apply_cvm_document, to_cvm_document
from infra.data.models.disclosures import CvmDocumentModel, CvmIssuerTickerModel

# SQLite caps the parameters of one statement; IN lists go in chunks.
CHUNK = 500


def _chunks(items: Sequence[str]) -> list[Sequence[str]]:
    return [items[i : i + CHUNK] for i in range(0, len(items), CHUNK)]


class SqlAlchemyIssuerTickerRepository(AbstractIssuerTickerRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_all(self, items: Sequence[IssuerTicker]) -> int:
        self.session.execute(delete(CvmIssuerTickerModel))
        unique = {i.ticker: i for i in items}
        for item in unique.values():
            self.session.add(
                CvmIssuerTickerModel(
                    ticker=item.ticker[:16],
                    cnpj=item.cnpj,
                    company_name=item.company_name[:200],
                    reference_date=item.reference_date,
                )
            )
        self.session.flush()
        return len(unique)

    def cnpjs_for(self, tickers: Sequence[str]) -> dict[str, str]:
        wanted = sorted({t.strip().upper() for t in tickers if t})
        out: dict[str, str] = {}
        for chunk in _chunks(wanted):
            stmt = select(CvmIssuerTickerModel.ticker, CvmIssuerTickerModel.cnpj).where(
                CvmIssuerTickerModel.ticker.in_(chunk)
            )
            out.update({t: c for t, c in self.session.execute(stmt).all()})
        return out


class SqlAlchemyCvmDocumentRepository(AbstractCvmDocumentRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_many(self, documents: Sequence[CvmDocument], *, seen_at: datetime) -> int:
        latest: dict[str, CvmDocument] = {}
        for doc in documents:
            current = latest.get(doc.protocol)
            if current is None or doc.version >= current.version:
                latest[doc.protocol] = doc
        protocols = sorted(latest)
        existing: dict[str, CvmDocumentModel] = {}
        for chunk in _chunks(protocols):
            stmt = select(CvmDocumentModel).where(CvmDocumentModel.protocol.in_(chunk))
            existing.update({m.protocol: m for m in self.session.scalars(stmt).all()})
        new = 0
        for protocol in protocols:
            doc = latest[protocol]
            model = existing.get(protocol)
            if model is None:
                created = apply_cvm_document(CvmDocumentModel(), doc)
                created.first_seen_at = seen_at
                self.session.add(created)
                new += 1
            elif doc.version > model.version:
                apply_cvm_document(model, doc)
        self.session.flush()
        return new

    def _filtered(self, stmt, cnpjs: Sequence[str], categories: Sequence[str]):  # noqa: ANN001, ANN202
        stmt = stmt.where(CvmDocumentModel.cnpj.in_(list(cnpjs)))
        if categories:
            stmt = stmt.where(CvmDocumentModel.category.in_(list(categories)))
        return stmt

    def list(
        self,
        cnpjs: Sequence[str],
        *,
        categories: Sequence[str] = (),
        unread_only: bool = False,
        since: date | None = None,
        limit: int = 50,
    ) -> list[CvmDocument]:
        if not cnpjs:
            return []
        stmt = self._filtered(select(CvmDocumentModel), cnpjs, categories)
        if unread_only:
            stmt = stmt.where(CvmDocumentModel.read_at.is_(None))
        if since is not None:
            stmt = stmt.where(CvmDocumentModel.delivery_date >= since)
        stmt = stmt.order_by(
            CvmDocumentModel.delivery_date.desc(), CvmDocumentModel.id.desc()
        ).limit(limit)
        return [to_cvm_document(m) for m in self.session.scalars(stmt).all()]

    def count_unread(self, cnpjs: Sequence[str], *, categories: Sequence[str] = ()) -> int:
        if not cnpjs:
            return 0
        stmt = self._filtered(select(func.count(CvmDocumentModel.id)), cnpjs, categories).where(
            CvmDocumentModel.read_at.is_(None)
        )
        return int(self.session.scalar(stmt) or 0)

    def category_counts(self, cnpjs: Sequence[str]) -> dict[str, int]:
        if not cnpjs:
            return {}
        stmt = (
            select(CvmDocumentModel.category, func.count(CvmDocumentModel.id))
            .where(CvmDocumentModel.cnpj.in_(list(cnpjs)))
            .group_by(CvmDocumentModel.category)
        )
        return {c: int(n) for c, n in self.session.execute(stmt).all()}

    def mark_read(self, ids: Sequence[int], *, read_at: datetime) -> int:
        if not ids:
            return 0
        result = self.session.execute(
            update(CvmDocumentModel)
            .where(CvmDocumentModel.id.in_(list(ids)), CvmDocumentModel.read_at.is_(None))
            .values(read_at=read_at)
        )
        return int(result.rowcount or 0)

    def mark_all_read(self, cnpjs: Sequence[str], *, read_at: datetime) -> int:
        if not cnpjs:
            return 0
        result = self.session.execute(
            update(CvmDocumentModel)
            .where(CvmDocumentModel.cnpj.in_(list(cnpjs)), CvmDocumentModel.read_at.is_(None))
            .values(read_at=read_at)
        )
        return int(result.rowcount or 0)

    def latest_delivery(self) -> date | None:
        return self.session.scalar(select(func.max(CvmDocumentModel.delivery_date)))
