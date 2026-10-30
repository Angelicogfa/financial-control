"""SQLAlchemy repositories of the CVM disclosures (Phase 28).

They take and return pure domain entities and never commit (the Unit of Work does).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from domain.disclosures.entities import CvmDocument, EventEffect, IssuerTicker
from domain.disclosures.repositories import (
    AbstractCvmDocumentRepository,
    AbstractCvmStatementRepository,
    AbstractIssuerTickerRepository,
    StatementLoad,
)
from domain.disclosures.statements import StatementDoc, StatementFact
from infra.data.mappers.disclosures import apply_cvm_document, to_cvm_document
from infra.data.models.disclosures import (
    CvmDocumentModel,
    CvmEventEffectModel,
    CvmIssuerTickerModel,
    CvmStatementFactModel,
    CvmStatementLoadModel,
)

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

    def all_cnpjs(self) -> set[str]:
        return set(self.session.scalars(select(CvmIssuerTickerModel.cnpj).distinct()).all())


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
                created.read_at = doc.read_at  # old news arrives read (see sync_documents)
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

    def unclassified(self, limit: int) -> list[CvmDocument]:
        stmt = (
            select(CvmDocumentModel)
            .where(CvmDocumentModel.event_class.is_(None))
            .order_by(CvmDocumentModel.id)
            .limit(limit)
        )
        return [to_cvm_document(m) for m in self.session.scalars(stmt).all()]

    def set_event_classes(self, classes: dict[int, str]) -> int:
        for doc_id, value in classes.items():
            self.session.execute(
                update(CvmDocumentModel)
                .where(CvmDocumentModel.id == doc_id)
                .values(event_class=value)
            )
        self.session.flush()
        return len(classes)

    def events(
        self, cnpjs: Sequence[str] | None = None, *, since: date | None = None
    ) -> list[CvmDocument]:
        base = select(CvmDocumentModel).where(
            CvmDocumentModel.event_class.is_not(None), CvmDocumentModel.event_class != ""
        )
        if since is not None:
            base = base.where(CvmDocumentModel.delivery_date >= since)
        if cnpjs is None:
            stmt = base.order_by(CvmDocumentModel.delivery_date, CvmDocumentModel.id)
            return [to_cvm_document(m) for m in self.session.scalars(stmt).all()]
        out: list[CvmDocument] = []
        for chunk in _chunks(sorted(set(cnpjs))):
            stmt = base.where(CvmDocumentModel.cnpj.in_(chunk))
            out.extend(to_cvm_document(m) for m in self.session.scalars(stmt).all())
        return sorted(out, key=lambda d: (d.delivery_date, d.id or 0))

    def replace_effects(self, effects: Sequence[EventEffect]) -> int:
        self.session.execute(delete(CvmEventEffectModel))
        rows = [
            {
                "document_id": e.document_id,
                "ticker": e.ticker,
                "event_date": e.event_date,
                "event_class": e.event_class,
                "car_1": e.car_1,
                "car_5": e.car_5,
                "car_20": e.car_20,
                "volatility_ratio": e.volatility_ratio,
                "confounded": e.confounded,
            }
            for e in effects
        ]
        for i in range(0, len(rows), CHUNK):
            self.session.execute(insert(CvmEventEffectModel), rows[i : i + CHUNK])
        self.session.flush()
        return len(rows)

    def effects(self, document_ids: Sequence[int] | None = None) -> list[EventEffect]:
        def entity(m: CvmEventEffectModel) -> EventEffect:
            return EventEffect(
                document_id=m.document_id,
                ticker=m.ticker,
                event_date=m.event_date,
                event_class=m.event_class,
                car_1=m.car_1,
                car_5=m.car_5,
                car_20=m.car_20,
                volatility_ratio=m.volatility_ratio,
                confounded=m.confounded,
            )

        if document_ids is None:
            return [entity(m) for m in self.session.scalars(select(CvmEventEffectModel)).all()]
        out: list[EventEffect] = []
        ids = sorted(set(document_ids))
        for i in range(0, len(ids), CHUNK):
            stmt = select(CvmEventEffectModel).where(
                CvmEventEffectModel.document_id.in_(ids[i : i + CHUNK])
            )
            out.extend(entity(m) for m in self.session.scalars(stmt).all())
        return out

    def latest_delivery(self) -> date | None:
        return self.session.scalar(select(func.max(CvmDocumentModel.delivery_date)))


def _fact(m: CvmStatementFactModel) -> StatementFact:
    return StatementFact(
        cnpj=m.cnpj,
        doc_type=m.doc_type,
        reference_date=m.reference_date,
        version=m.version,
        delivered_on=m.delivered_on,
        basis=m.basis,
        template=m.template,
        metric=m.metric,
        period_start=m.period_start,
        period_end=m.period_end,
        value=m.value,
    )


class SqlAlchemyCvmStatementRepository(AbstractCvmStatementRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def known_docs(self, doc_type: str, year: int) -> set[tuple[str, date, int]]:
        stmt = (
            select(
                CvmStatementFactModel.cnpj,
                CvmStatementFactModel.reference_date,
                CvmStatementFactModel.version,
            )
            .where(
                CvmStatementFactModel.doc_type == doc_type,
                CvmStatementFactModel.reference_date >= date(year, 1, 1),
                CvmStatementFactModel.reference_date <= date(year, 12, 31),
            )
            .distinct()
        )
        return {(c, r, v) for c, r, v in self.session.execute(stmt).all()}

    def add_many(self, facts: Sequence[StatementFact]) -> int:
        unique = {(f.cnpj, f.doc_type, f.reference_date, f.version, f.metric): f for f in facts}
        if not unique:
            return 0
        rows = [
            {
                "cnpj": f.cnpj,
                "doc_type": f.doc_type,
                "reference_date": f.reference_date,
                "version": f.version,
                "metric": f.metric,
                "delivered_on": f.delivered_on,
                "basis": f.basis,
                "template": f.template,
                "period_start": f.period_start,
                "period_end": f.period_end,
                "value": f.value,
            }
            for f in unique.values()
        ]
        for i in range(0, len(rows), CHUNK):
            self.session.execute(insert(CvmStatementFactModel), rows[i : i + CHUNK])
        self.session.flush()
        return len(rows)

    def facts_for(self, cnpj: str) -> list[StatementFact]:
        stmt = (
            select(CvmStatementFactModel)
            .where(CvmStatementFactModel.cnpj == cnpj)
            .order_by(CvmStatementFactModel.delivered_on, CvmStatementFactModel.reference_date)
        )
        return [_fact(m) for m in self.session.scalars(stmt).all()]

    def cnpjs_with_statements(self) -> set[str]:
        return set(self.session.scalars(select(CvmStatementFactModel.cnpj).distinct()).all())

    def docs_for(self, cnpj: str) -> list[StatementDoc]:
        stmt = (
            select(
                CvmStatementFactModel.doc_type,
                CvmStatementFactModel.reference_date,
                CvmStatementFactModel.version,
                CvmStatementFactModel.delivered_on,
            )
            .where(CvmStatementFactModel.cnpj == cnpj)
            .distinct()
            .order_by(CvmStatementFactModel.delivered_on.desc())
        )
        return [
            StatementDoc(cnpj=cnpj, doc_type=t, reference_date=r, version=v, delivered_on=d)
            for t, r, v, d in self.session.execute(stmt).all()
        ]

    def record_load(self, load: StatementLoad) -> None:
        row = self.session.get(CvmStatementLoadModel, (load.doc_type, load.year))
        if row is None:
            row = CvmStatementLoadModel(doc_type=load.doc_type, year=load.year)
            self.session.add(row)
        row.source_stamp = load.source_stamp[:64]
        row.facts = load.facts
        row.loaded_at = load.loaded_at
        self.session.flush()

    def loads(self) -> list[StatementLoad]:
        stmt = select(CvmStatementLoadModel).order_by(
            CvmStatementLoadModel.doc_type, CvmStatementLoadModel.year
        )
        return [
            StatementLoad(
                doc_type=m.doc_type,
                year=m.year,
                source_stamp=m.source_stamp,
                facts=m.facts,
                loaded_at=m.loaded_at,
            )
            for m in self.session.scalars(stmt).all()
        ]
