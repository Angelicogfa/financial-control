"""Disclosure feed of the held and followed companies (Phase 28.4)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from controllers.disclosures.requests import MarkReadRequest
from controllers.disclosures.responses import CvmDocumentDTO, DisclosureFeedDTO
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.disclosures.entities import CvmDocument
from domain.disclosures.services.sync import COMPANY_TYPES, base_ticker, company_assets
from domain.shared.entities import AssetEntity
from domain.shared.unit_of_work import AbstractUnitOfWork

NOT_COVERED_NOTE = (
    "FIIs e ETFs não são companhias abertas e não publicam no IPE da CVM: os comunicados "
    "deles não aparecem aqui."
)


def to_document_dto(doc: CvmDocument, tickers: Sequence[str]) -> CvmDocumentDTO:
    return CvmDocumentDTO(
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
        tickers_by_cnpj: dict[str, list[str]] = {}
        for ticker, cnpj in sorted(cnpj_by_ticker.items()):
            tickers_by_cnpj.setdefault(cnpj, []).append(ticker)
        return DisclosureFeedDTO(
            items=[to_document_dto(d, tickers_by_cnpj.get(d.cnpj, [])) for d in docs],
            unread_count=unread,
            category_counts=counts,
            companies=len(tickers),
            unmapped=[t for t in tickers if t not in cnpj_by_ticker],
            latest_delivery=last,
            note=NOT_COVERED_NOTE if not_covered or asset_id is None else None,
        )

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
