"""Use cases (command/query handlers) for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from dataclasses import replace

from controllers.assets.requests import AssetCreateRequest, AssetUpdateRequest, CerradoUpdateRequest
from controllers.assets.responses import (
    ArcaSuggestionDTO,
    AssetAnalysisResponseDTO,
    AssetPriceHistoryDTO,
    AssetResponseDTO,
    DatedPriceDTO,
    PricePointDTO,
)
from controllers.assets.serializers import to_asset_analysis_dto, to_asset_dto
from controllers.shared.dependencies import UoWFactory
from controllers.shared.responses import PaginatedResponse
from controllers.shared.serializers import to_page_meta_dto
from core.errors import ConflictError, NotFoundError, ValidationError
from core.helpers.pagination import PaginationParams
from domain.assets.services.codes import CODE_ASSET_TYPES, generated_asset_code
from domain.assets.services.etf_exposure import suggest_arca_class
from domain.market.services.price_chart import PRICE_RANGES
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AssetEntity, ChecklistAnswer, FixedIncomeTermEntity
from domain.shared.enums import AssetLifecycle, AssetType


class AssetHandler:
    """Application handler for Asset commands and queries (opens UoW transaction boundaries)."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        arca_class: str | None = None,
        asset_type: str | None = None,
        use_cerrado: bool | None = None,
        active_only: bool = True,
    ) -> PaginatedResponse[AssetResponseDTO]:
        with self.uow_factory() as uow:
            result = uow.assets.list_paginated(
                params,
                arca_class=arca_class,
                asset_type=asset_type,
                use_cerrado=use_cerrado,
                active_only=active_only,
            )
            lifecycles = self.portfolio_service.asset_lifecycles(uow, result.items)
            return PaginatedResponse(
                items=[_with_lifecycle(to_asset_dto(a), lifecycles) for a in result.items],
                meta=to_page_meta_dto(result.meta),
            )

    @staticmethod
    def suggest_classification(ticker: str, asset_type: AssetType) -> ArcaSuggestionDTO:
        suggestion = suggest_arca_class(ticker, asset_type)
        return ArcaSuggestionDTO(
            ticker=ticker.strip().upper(),
            asset_type=asset_type,
            arca_class=suggestion.arca_class,
            source=suggestion.source,
            reason=suggestion.reason,
        )

    def get_by_id(self, asset_id: int) -> AssetResponseDTO:
        with self.uow_factory() as uow:
            entity = uow.assets.get_by_id(asset_id)
            if entity is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            lifecycles = self.portfolio_service.asset_lifecycles(uow, [entity])
            return _with_lifecycle(to_asset_dto(entity), lifecycles)

    def create(self, req: AssetCreateRequest) -> AssetResponseDTO:
        with self.uow_factory() as uow:
            if req.ticker is not None and uow.assets.get_by_ticker(req.ticker) is not None:
                raise ConflictError(
                    f"Asset with ticker '{req.ticker.upper()}' already exists",
                    code="DUPLICATE_TICKER",
                )
            if req.ticker is None and req.asset_type not in CODE_ASSET_TYPES:
                raise ValidationError(
                    "ticker is required for exchange-traded assets", code="TICKER_REQUIRED"
                )

            fi_term = None
            if req.fixed_income_term is not None:
                t = req.fixed_income_term
                fi_term = FixedIncomeTermEntity(
                    instrument_kind=t.instrument_kind,
                    indexer=t.indexer,
                    contracted_rate=t.contracted_rate,
                    issue_date=t.issue_date,
                    maturity_date=t.maturity_date,
                    tax_exempt=t.tax_exempt,
                    liquidity=t.liquidity,
                    issuer=t.issuer,
                    semiannual_coupons=t.semiannual_coupons,
                )

            ticker = req.ticker or generated_asset_code(
                req.asset_type,
                req.name,
                fi_term,
                is_taken=lambda code: uow.assets.get_by_ticker(code) is not None,
            )
            entity = AssetEntity(
                ticker=ticker,
                name=req.name,
                asset_type=req.asset_type,
                arca_class=req.arca_class or suggest_arca_class(ticker, req.asset_type).arca_class,
                currency=req.currency,
                manual_price=req.manual_price,
                custom_class_weight=req.custom_class_weight,
                use_cerrado=req.use_cerrado,
                cerrado_answers=dict(req.cerrado_answers),
                checklist_profile=req.checklist_profile,
                notes=req.notes,
                purpose=req.purpose,
                fixed_income_term=fi_term,
            )
            created = uow.assets.add(entity)
            uow.commit()
            return to_asset_dto(created)

    def update(self, asset_id: int, req: AssetUpdateRequest) -> AssetResponseDTO:
        with self.uow_factory() as uow:
            current = uow.assets.get_by_id(asset_id)
            if current is None:
                raise NotFoundError(f"Asset id={asset_id} not found")

            fi_term = current.fixed_income_term
            if req.fixed_income_term is not None:
                t = req.fixed_income_term
                fi_term = FixedIncomeTermEntity(
                    instrument_kind=t.instrument_kind,
                    indexer=t.indexer,
                    contracted_rate=t.contracted_rate,
                    issue_date=t.issue_date,
                    maturity_date=t.maturity_date,
                    tax_exempt=t.tax_exempt,
                    liquidity=t.liquidity,
                    issuer=t.issuer,
                    semiannual_coupons=t.semiannual_coupons,
                )

            updated_entity = replace(
                current,
                ticker=req.ticker if req.ticker is not None else current.ticker,
                name=req.name if req.name is not None else current.name,
                asset_type=req.asset_type if req.asset_type is not None else current.asset_type,
                arca_class=req.arca_class if req.arca_class is not None else current.arca_class,
                currency=req.currency if req.currency is not None else current.currency,
                manual_price=(
                    req.manual_price if req.manual_price is not None else current.manual_price
                ),
                custom_class_weight=(
                    req.custom_class_weight
                    if req.custom_class_weight is not None
                    else current.custom_class_weight
                ),
                use_cerrado=(
                    req.use_cerrado if req.use_cerrado is not None else current.use_cerrado
                ),
                cerrado_answers=(
                    dict(req.cerrado_answers)
                    if req.cerrado_answers is not None
                    else current.cerrado_answers
                ),
                checklist_profile=(
                    req.checklist_profile
                    if req.checklist_profile is not None
                    else current.checklist_profile
                ),
                is_active=req.is_active if req.is_active is not None else current.is_active,
                notes=req.notes if req.notes is not None else current.notes,
                purpose=req.purpose if req.purpose is not None else current.purpose,
                fixed_income_term=fi_term,
            )
            saved = uow.assets.update(updated_entity)
            uow.commit()
            return to_asset_dto(saved)

    def update_cerrado(self, asset_id: int, req: CerradoUpdateRequest) -> AssetResponseDTO:
        with self.uow_factory() as uow:
            current = uow.assets.get_by_id(asset_id)
            if current is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            answers = {}
            for qid, raw in req.cerrado_answers.items():
                answer = ChecklistAnswer.coerce(qid, raw)
                if answer.value is not None:
                    answers[qid] = replace(answer, evidence=req.evidence.get(qid) or None)
            updated_entity = replace(
                current,
                use_cerrado=req.use_cerrado,
                cerrado_answers=answers,
                checklist_profile=req.checklist_profile or current.checklist_profile,
                custom_class_weight=req.custom_class_weight,
            )
            saved = uow.assets.update(updated_entity)
            reloaded = uow.assets.get_by_id(asset_id) or saved
            self.portfolio_service.record_checklist(
                uow, reloaded, self.portfolio_service.evaluate_checklist(uow, reloaded)
            )
            uow.commit()
            return to_asset_dto(reloaded)

    def delete(self, asset_id: int, *, hard: bool = False) -> None:
        with self.uow_factory() as uow:
            found = uow.assets.delete(asset_id, hard=hard)
            if not found:
                raise NotFoundError(f"Asset id={asset_id} not found")
            uow.commit()

    def get_analysis(self, asset_id: int) -> AssetAnalysisResponseDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            raw = self.portfolio_service.analyze_single_asset(uow, asset)
            payload = to_asset_analysis_dto(asset, raw)
            return AssetAnalysisResponseDTO(**payload)

    def get_prices(self, asset_id: int, range_period: str) -> AssetPriceHistoryDTO:
        if range_period not in PRICE_RANGES:
            raise ValidationError(f"range must be one of {', '.join(PRICE_RANGES)}")
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
        chart = self.portfolio_service.price_chart(asset, range_period)
        return AssetPriceHistoryDTO(
            range=range_period,
            points=[PricePointDTO(date=d, close=c) for d, c in chart.points],
            change=chart.change,
            high=DatedPriceDTO(date=chart.high[0], price=chart.high[1]) if chart.high else None,
            low=DatedPriceDTO(date=chart.low[0], price=chart.low[1]) if chart.low else None,
            dropped_spikes=chart.dropped_spikes,
        )


def _with_lifecycle(
    dto: AssetResponseDTO, lifecycles: dict[int, tuple[AssetLifecycle, bool]]
) -> AssetResponseDTO:
    status, eligible = lifecycles.get(dto.id, (None, None))
    return dto.model_copy(update={"lifecycle_status": status, "eligible": eligible})
