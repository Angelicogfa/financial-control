"""Bidirectional mappers between SQLAlchemy ORM models and pure Domain Entities."""

from __future__ import annotations

from decimal import Decimal

from fincontrol_core.domain.entities import (
    ArcaTargetEntity,
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    IntraClassStrategy,
    SeriesUnit,
    TransactionKind,
)

from fincontrol_persistence.models import (
    ArcaTargetModel,
    AssetModel,
    EarningModel,
    FixedIncomeTermModel,
    MarketSeriesModel,
    PortfolioSnapshotModel,
    TransactionModel,
)


def to_fixed_income_term_entity(model: FixedIncomeTermModel) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        id=model.id,
        asset_id=model.asset_id,
        instrument_kind=FixedIncomeInstrumentKind(model.instrument_kind),
        indexer=FixedIncomeIndexer(model.indexer),
        contracted_rate=Decimal(model.contracted_rate),
        issue_date=model.issue_date,
        maturity_date=model.maturity_date,
        tax_exempt=bool(model.tax_exempt),
        liquidity=FixedIncomeLiquidity(model.liquidity),
        issuer=model.issuer,
    )


def to_fixed_income_term_model(entity: FixedIncomeTermEntity) -> FixedIncomeTermModel:
    return FixedIncomeTermModel(
        instrument_kind=entity.instrument_kind.value,
        indexer=entity.indexer.value,
        contracted_rate=entity.contracted_rate,
        issue_date=entity.issue_date,
        maturity_date=entity.maturity_date,
        tax_exempt=entity.tax_exempt,
        liquidity=entity.liquidity.value,
        issuer=entity.issuer,
    )


def to_transaction_entity(model: TransactionModel) -> TransactionEntity:
    return TransactionEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=TransactionKind(model.kind),
        trade_date=model.trade_date,
        quantity=Decimal(model.quantity),
        unit_price=Decimal(model.unit_price),
        fees=Decimal(model.fees),
        fx_rate=Decimal(model.fx_rate),
        notes=model.notes,
        created_at=model.created_at,
    )


def to_earning_entity(model: EarningModel) -> EarningEntity:
    return EarningEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=EarningKind(model.kind),
        payment_date=model.payment_date,
        ex_date=model.ex_date,
        gross_amount=Decimal(model.gross_amount),
        withholding_tax=Decimal(model.withholding_tax),
        net_amount=Decimal(model.net_amount),
        notes=model.notes,
        created_at=model.created_at,
    )


def to_asset_entity(
    model: AssetModel,
    *,
    include_children: bool = True,
) -> AssetEntity:
    fi_term = (
        to_fixed_income_term_entity(model.fixed_income_term)
        if model.fixed_income_term is not None
        else None
    )
    txs: tuple[TransactionEntity, ...] = ()
    earnings: tuple[EarningEntity, ...] = ()
    if include_children:
        txs = tuple(to_transaction_entity(t) for t in model.transactions)
        earnings = tuple(to_earning_entity(e) for e in model.earnings)

    return AssetEntity(
        id=model.id,
        ticker=model.ticker,
        name=model.name,
        asset_type=AssetType(model.asset_type),
        arca_class=ArcaClass(model.arca_class),
        currency=model.currency,
        manual_price=Decimal(model.manual_price) if model.manual_price is not None else None,
        custom_class_weight=(
            Decimal(model.custom_class_weight) if model.custom_class_weight is not None else None
        ),
        use_cerrado=bool(model.use_cerrado),
        cerrado_answers=dict(model.cerrado_answers or {}),
        is_active=bool(model.is_active),
        notes=model.notes,
        fixed_income_term=fi_term,
        transactions=txs,
        earnings=earnings,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_arca_target_entity(model: ArcaTargetModel) -> ArcaTargetEntity:
    return ArcaTargetEntity(
        arca_class=ArcaClass(model.arca_class),
        target_pct=Decimal(model.target_pct),
        intra_class_strategy=IntraClassStrategy(model.intra_class_strategy),
        updated_at=model.updated_at,
    )


def to_market_series_point(model: MarketSeriesModel) -> MarketSeriesPoint:
    return MarketSeriesPoint(
        id=model.id,
        symbol=model.symbol,
        reference_date=model.reference_date,
        value=float(model.value),
        unit=SeriesUnit(model.unit),
    )


def to_portfolio_snapshot_entity(model: PortfolioSnapshotModel) -> PortfolioSnapshotEntity:
    return PortfolioSnapshotEntity(
        snapshot_date=model.snapshot_date,
        invested_value=float(model.invested_value),
        market_value=float(model.market_value),
        unrealized_pnl=float(model.unrealized_pnl),
        realized_pnl_cum=float(model.realized_pnl_cum),
        earnings_cum=float(model.earnings_cum),
        consolidated_pnl=float(model.consolidated_pnl),
        net_flow=float(model.net_flow),
        by_class=dict(model.by_class or {}),
    )
