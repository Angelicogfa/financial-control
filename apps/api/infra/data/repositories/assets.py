"""SQLAlchemy repositories: assets, fixed income terms and checklist answers/evaluations.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from core.errors import NotFoundError, ValidationError
from core.helpers.pagination import PaginatedResult, PaginationParams
from domain.shared.entities import (
    AssetEntity,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
)
from domain.shared.enums import AnswerSource
from domain.shared.repositories import (
    AbstractAssetRepository,
    AbstractChecklistRepository,
)
from infra.data.mappers.assets import (
    current_answers,
    to_asset_entity,
    to_checklist_answer,
    to_checklist_evaluation,
    to_fixed_income_term_model,
)
from infra.data.models.assets import (
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
)
from infra.data.repositories.common import apply_sort_and_paginate


def _append_changed_answers(model: AssetModel, answers: Mapping[str, ChecklistAnswer]) -> None:
    """Append a row for every answer that differs from the stored one (append-only, 11.4).

    Questions answered before and missing from `answers` get a cleared (NULL) row.
    """
    current = current_answers(model.checklist_answers)
    now = datetime.now(UTC)
    for qid in sorted(set(current) | set(answers)):
        new = answers.get(qid)
        old = current.get(qid)
        if new is None and old is None:
            continue
        if (
            new is not None
            and old is not None
            and new.value == old.value
            and new.evidence in (None, old.evidence)
        ):
            continue
        model.checklist_answers.append(
            ChecklistAnswerModel(
                question_id=qid,
                value=new.value.value if new is not None and new.value else None,
                source=(new.source if new is not None else AnswerSource.MANUAL).value,
                evidence=new.evidence if new is not None else None,
                answered_at=(new.answered_at if new is not None and new.answered_at else now),
                checklist_version=new.checklist_version if new is not None else 2,
            )
        )


class SqlAlchemyAssetRepository(AbstractAssetRepository):
    """SQLAlchemy implementation of AbstractAssetRepository."""

    SORT_COLUMNS = {
        "id": AssetModel.id,
        "ticker": AssetModel.ticker,
        "name": AssetModel.name,
        "asset_type": AssetModel.asset_type,
        "arca_class": AssetModel.arca_class,
        "created_at": AssetModel.created_at,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, asset: AssetEntity) -> AssetEntity:
        model = AssetModel.create(
            ticker=asset.ticker,
            name=asset.name,
            asset_type=asset.asset_type,
            arca_class=asset.arca_class,
            currency=asset.currency,
            manual_price=asset.manual_price,
            custom_class_weight=asset.custom_class_weight,
            use_cerrado=asset.use_cerrado,
            is_active=asset.is_active,
            notes=asset.notes,
        )
        model.purpose = asset.purpose.value
        model.checklist_profile = asset.checklist_profile.value if asset.checklist_profile else None
        if asset.fixed_income_term is not None:
            model.fixed_income_term = to_fixed_income_term_model(asset.fixed_income_term)
        self.session.add(model)
        self.session.flush()
        _append_changed_answers(model, asset.cerrado_answers)
        self.session.flush()
        return to_asset_entity(model, include_children=False)

    def update(self, asset: AssetEntity) -> AssetEntity:
        if asset.id is None:
            raise ValidationError("Cannot update AssetEntity without id")
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.checklist_answers),
                selectinload(AssetModel.corporate_events),
            )
            .where(AssetModel.id == asset.id)
        )
        model = self.session.scalar(stmt)
        if model is None:
            raise NotFoundError(f"Asset id={asset.id} not found")

        model.ticker = asset.ticker
        model.name = asset.name
        model.asset_type = asset.asset_type.value
        model.arca_class = asset.arca_class.value if asset.arca_class else model.arca_class
        model.currency = asset.currency or model.currency
        model.manual_price = asset.manual_price
        model.custom_class_weight = asset.custom_class_weight
        model.use_cerrado = asset.use_cerrado
        model.checklist_profile = asset.checklist_profile.value if asset.checklist_profile else None
        _append_changed_answers(model, asset.cerrado_answers)
        model.is_active = asset.is_active
        model.notes = asset.notes
        model.purpose = asset.purpose.value

        if asset.fixed_income_term is not None:
            term = asset.fixed_income_term
            if model.fixed_income_term is None:
                model.fixed_income_term = to_fixed_income_term_model(term)
            else:
                model.fixed_income_term.instrument_kind = term.instrument_kind.value
                model.fixed_income_term.indexer = term.indexer.value
                model.fixed_income_term.contracted_rate = term.contracted_rate
                model.fixed_income_term.issue_date = term.issue_date
                model.fixed_income_term.maturity_date = term.maturity_date
                model.fixed_income_term.tax_exempt = term.tax_exempt
                model.fixed_income_term.liquidity = term.liquidity.value
                model.fixed_income_term.issuer = term.issuer
        elif model.fixed_income_term is not None:
            model.fixed_income_term = None

        self.session.flush()
        return to_asset_entity(model, include_children=False)

    def get_by_id(self, asset_id: int) -> AssetEntity | None:
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.transactions),
                selectinload(AssetModel.earnings),
                selectinload(AssetModel.checklist_answers),
                selectinload(AssetModel.corporate_events),
            )
            .where(AssetModel.id == asset_id)
        )
        model = self.session.scalar(stmt)
        return to_asset_entity(model, include_children=True) if model else None

    def get_by_ticker(self, ticker: str) -> AssetEntity | None:
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.transactions),
                selectinload(AssetModel.earnings),
                selectinload(AssetModel.checklist_answers),
                selectinload(AssetModel.corporate_events),
            )
            .where(AssetModel.ticker == ticker.strip().upper())
        )
        model = self.session.scalar(stmt)
        return to_asset_entity(model, include_children=True) if model else None

    def list_all(self, *, active_only: bool = True) -> list[AssetEntity]:
        stmt = select(AssetModel).options(
            selectinload(AssetModel.fixed_income_term),
            selectinload(AssetModel.transactions),
            selectinload(AssetModel.earnings),
            selectinload(AssetModel.checklist_answers),
            selectinload(AssetModel.corporate_events),
        )
        if active_only:
            stmt = stmt.where(AssetModel.is_active.is_(True))
        stmt = stmt.order_by(AssetModel.ticker.asc())
        models = list(self.session.scalars(stmt).all())
        return [to_asset_entity(m, include_children=True) for m in models]

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        arca_class: str | None = None,
        asset_type: str | None = None,
        use_cerrado: bool | None = None,
        active_only: bool = True,
    ) -> PaginatedResult[AssetEntity]:
        stmt = select(AssetModel).options(
            selectinload(AssetModel.fixed_income_term),
            selectinload(AssetModel.transactions),
            selectinload(AssetModel.earnings),
            selectinload(AssetModel.checklist_answers),
            selectinload(AssetModel.corporate_events),
        )
        if active_only:
            stmt = stmt.where(AssetModel.is_active.is_(True))
        if arca_class:
            stmt = stmt.where(AssetModel.arca_class == arca_class.upper())
        if asset_type:
            stmt = stmt.where(AssetModel.asset_type == asset_type.upper())
        if use_cerrado is not None:
            stmt = stmt.where(AssetModel.use_cerrado.is_(use_cerrado))
        if params.search:
            pattern = f"%{params.search.strip()}%"
            stmt = stmt.where(or_(AssetModel.ticker.ilike(pattern), AssetModel.name.ilike(pattern)))

        rows, meta = apply_sort_and_paginate(
            self.session, stmt, params, self.SORT_COLUMNS, AssetModel.ticker, AssetModel.id
        )
        return PaginatedResult(
            items=[to_asset_entity(m, include_children=True) for m in rows],
            meta=meta,
        )

    def delete(self, asset_id: int, *, hard: bool = False) -> bool:
        model = self.session.get(AssetModel, asset_id)
        if model is None:
            return False
        if hard:
            self.session.delete(model)
        else:
            model.is_active = False
        self.session.flush()
        return True


class SqlAlchemyChecklistRepository(AbstractChecklistRepository):
    """SQLAlchemy implementation of AbstractChecklistRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def answer_history(self, asset_id: int) -> list[ChecklistAnswer]:
        stmt = (
            select(ChecklistAnswerModel)
            .where(ChecklistAnswerModel.asset_id == asset_id)
            .order_by(ChecklistAnswerModel.answered_at.desc(), ChecklistAnswerModel.id.desc())
        )
        return [to_checklist_answer(m) for m in self.session.scalars(stmt).all()]

    def record_evaluation(self, record: ChecklistEvaluationRecord) -> ChecklistEvaluationRecord:
        model = ChecklistEvaluationModel(
            asset_id=record.asset_id,
            evaluated_at=record.evaluated_at,
            profile=record.profile.value,
            checklist_version=record.checklist_version,
            score=record.score,
            normalized_score=record.normalized_score,
            coverage_pct=record.coverage_pct,
            answered=record.answered,
            applicable=record.applicable,
            recommendation=record.recommendation,
        )
        self.session.add(model)
        self.session.flush()
        return to_checklist_evaluation(model)

    def latest_evaluation(self, asset_id: int) -> ChecklistEvaluationRecord | None:
        history = self.evaluation_history(asset_id, limit=1)
        return history[-1] if history else None

    def evaluation_history(
        self, asset_id: int, *, limit: int = 104
    ) -> list[ChecklistEvaluationRecord]:
        stmt = (
            select(ChecklistEvaluationModel)
            .where(ChecklistEvaluationModel.asset_id == asset_id)
            .order_by(
                ChecklistEvaluationModel.evaluated_at.desc(), ChecklistEvaluationModel.id.desc()
            )
            .limit(limit)
        )
        rows = [to_checklist_evaluation(m) for m in self.session.scalars(stmt).all()]
        return rows[::-1]
