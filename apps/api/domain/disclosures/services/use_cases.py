"""Disclosure feed of the held and followed companies (Phase 28.4)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from controllers.disclosures.requests import MarkReadRequest
from controllers.disclosures.responses import (
    CvmDocumentDTO,
    DisclosureFeedDTO,
    EventClassDTO,
    EventHorizonDTO,
    EventReactionDTO,
    EventStudyDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.disclosures.entities import CvmDocument, EventEffect
from domain.disclosures.events import EVENT_LABELS
from domain.disclosures.services.sync import COMPANY_TYPES, base_ticker, company_assets
from domain.forecast.event_runs import EVENTS
from domain.forecast.events import EventStudy
from domain.shared.entities import AssetEntity
from domain.shared.unit_of_work import AbstractUnitOfWork

NOT_COVERED_NOTE = (
    "FIIs e ETFs não são companhias abertas e não publicam no IPE da CVM: os comunicados "
    "deles não aparecem aqui."
)


def to_document_dto(
    doc: CvmDocument,
    tickers: Sequence[str],
    effect: EventEffect | None = None,
    typical: float | None = None,
) -> CvmDocumentDTO:
    return CvmDocumentDTO(
        event_class=doc.event_class or None,
        event_label=EVENT_LABELS.get(doc.event_class or "") if doc.event_class else None,
        reaction=EventReactionDTO(
            event_date=effect.event_date,
            car_1=effect.car_1,
            car_5=effect.car_5,
            car_20=effect.car_20,
            confounded=effect.confounded,
        )
        if effect is not None
        else None,
        typical_20=typical,
        id=doc.id,  # type: ignore[arg-type]
        protocol=doc.protocol,
        tickers=list(tickers),
        company_name=doc.company_name,
        category=doc.category,
        doc_type=doc.doc_type,
        species=doc.species,
        subject=doc.subject,
        reference_date=doc.reference_date,
        delivery_date=doc.delivery_date,
        version=doc.version,
        link=doc.link,
        read=doc.read_at is not None,
        first_seen_at=doc.first_seen_at,
    )


class DisclosureHandler:
    """Relevant facts, market and shareholder notices from the CVM (IPE)."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def _scope(
        self, uow: AbstractUnitOfWork, asset_id: int | None
    ) -> tuple[list[AssetEntity], bool]:
        """The companies to show and whether a requested asset is out of the IPE."""
        if asset_id is None:
            return company_assets(uow.assets.list_all(active_only=True)), False
        asset = uow.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError(f"Asset {asset_id} not found")
        return ([asset], False) if asset.asset_type in COMPANY_TYPES else ([], True)

    def feed(
        self,
        *,
        asset_id: int | None = None,
        categories: Sequence[str] = (),
        unread_only: bool = False,
        limit: int = 50,
    ) -> DisclosureFeedDTO:
        with self.uow_factory() as uow:
            assets, not_covered = self._scope(uow, asset_id)
            tickers = sorted({base_ticker(a.ticker) for a in assets})
            cnpj_by_ticker = uow.cvm_issuers.cnpjs_for(tickers)
            cnpjs = sorted(set(cnpj_by_ticker.values()))
            docs = uow.cvm_documents.list(
                cnpjs, categories=categories, unread_only=unread_only, limit=limit
            )
            unread = uow.cvm_documents.count_unread(cnpjs)
            counts = uow.cvm_documents.category_counts(cnpjs)
            last = uow.cvm_documents.latest_delivery()
            effects = {
                e.document_id: e
                for e in uow.cvm_documents.effects([d.id for d in docs if d.id is not None])
            }
            stored = uow.forecasts.latest_model(EVENTS)
        found = EventStudy.from_dict(stored.payload) if stored is not None else None

        def typical(doc: CvmDocument) -> float | None:
            effect = found.effect(doc.event_class, 20) if found and doc.event_class else None
            return effect.effect if effect is not None else None

        tickers_by_cnpj: dict[str, list[str]] = {}
        for ticker, cnpj in sorted(cnpj_by_ticker.items()):
            tickers_by_cnpj.setdefault(cnpj, []).append(ticker)
        return DisclosureFeedDTO(
            items=[
                to_document_dto(
                    d, tickers_by_cnpj.get(d.cnpj, []), effects.get(d.id or 0), typical(d)
                )
                for d in docs
            ],
            unread_count=unread,
            category_counts=counts,
            companies=len(tickers),
            unmapped=[t for t in tickers if t not in cnpj_by_ticker],
            latest_delivery=last,
            note=NOT_COVERED_NOTE if not_covered or asset_id is None else None,
        )

    def event_study(self) -> EventStudyDTO:
        """What usually happens to the price after each kind of event (Phase 42.4)."""
        with self.uow_factory() as uow:
            stored = uow.forecasts.latest_model(EVENTS)
        if stored is None:
            return EventStudyDTO(status="NOT_COMPUTED")
        found = EventStudy.from_dict(stored.payload)
        return EventStudyDTO(
            status="OK",
            as_of=found.as_of,
            events=found.events,
            confounded=found.confounded,
            sign_threshold=found.sign_threshold,
            classes=[
                EventClassDTO(
                    event_class=c.event_class,
                    label=EVENT_LABELS.get(c.event_class, c.event_class),
                    events=c.events,
                    horizons=[
                        EventHorizonDTO(
                            horizon=h.horizon,
                            events=h.events,
                            mean=h.mean,
                            effect=h.effect,
                            effect_sd=h.effect_sd,
                            sign_probability=h.sign_probability,
                        )
                        for h in c.horizons
                    ],
                    volatility_ratio=c.volatility_ratio,
                    **self._gate_fields(found, c.event_class),
                )
                for c in sorted(found.classes, key=lambda c: -c.events)
            ],
        )

    @staticmethod
    def _gate_fields(found: EventStudy, event_class: str) -> dict:
        verdict = found.gate(event_class)
        if verdict is None:
            return {"gate_reason": "O portão fora da amostra ainda não foi calculado."}
        return {
            "passed": verdict.passed,
            "gate_reason": verdict.reason,
            "oos_origins": verdict.origins,
            "oos_improvement": verdict.improvement if verdict.origins else None,
            "oos_win_share": verdict.win_share if verdict.origins else None,
        }

    def mark_read(self, req: MarkReadRequest, *, now: datetime | None = None) -> int:
        """Mark the given documents (or every document in scope) as read."""
        read_at = now or datetime.now(UTC)
        with self.uow_factory() as uow:
            if req.all:
                assets, _ = self._scope(uow, req.asset_id)
                cnpjs = sorted(
                    set(uow.cvm_issuers.cnpjs_for([base_ticker(a.ticker) for a in assets]).values())
                )
                changed = uow.cvm_documents.mark_all_read(cnpjs, read_at=read_at)
            else:
                changed = uow.cvm_documents.mark_read(req.ids, read_at=read_at)
            uow.commit()
        return changed
