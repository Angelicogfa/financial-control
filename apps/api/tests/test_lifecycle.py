"""Unit tests for the asset lifecycle and eligibility rules (item 10.6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.assets.services.cerrado import evaluate
from domain.market.entities import Quote
from domain.policy.services.allocation import ArcaTargets
from domain.policy.services.lifecycle import has_position, is_eligible, lifecycle_status
from domain.policy.services.policy import EligibilityPolicy
from domain.portfolio.services.consolidation import consolidate_portfolio, plan_contribution
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import (
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    TransactionKind,
)

GOOD = {"roe": True, "debt": True, "governance": True}
BAD = {"roe": False, "debt": False, "governance": True}


def _tx(kind: TransactionKind, qty: str, price: str = "10") -> TransactionEntity:
    return TransactionEntity(
        asset_id=1,
        kind=kind,
        trade_date=date(2025, 1, 2),
        quantity=Decimal(qty),
        unit_price=Decimal(price),
    )


def test_eligibility_rules() -> None:
    default = EligibilityPolicy()
    strict = EligibilityPolicy(require_evaluation=True, min_score=2, min_coverage_pct=25.0)
    unanswered = evaluate(AssetType.STOCK_BR, {})
    good = evaluate(AssetType.STOCK_BR, GOOD)  # 3 of 12 answered, score 3
    bad = evaluate(AssetType.STOCK_BR, BAD)

    assert is_eligible(unanswered, default)
    assert not is_eligible(unanswered, strict)
    assert is_eligible(good, default) and is_eligible(good, strict)
    assert not is_eligible(bad, default)
    assert not is_eligible(good, EligibilityPolicy(min_coverage_pct=50.0))
    assert is_eligible(bad, default, AssetPurpose.EMERGENCY_RESERVE)
    assert is_eligible(evaluate(AssetType.STOCK_BR, BAD, use_cerrado=False), default)


@pytest.mark.parametrize(
    ("active", "holds", "eligible", "expected"),
    [
        (False, True, True, AssetLifecycle.ARCHIVED),
        (True, True, True, AssetLifecycle.HELD),
        (True, True, False, AssetLifecycle.REVIEW),
        (True, False, True, AssetLifecycle.ELIGIBLE),
        (True, False, False, AssetLifecycle.WATCHLIST),
    ],
)
def test_lifecycle_matrix(active: bool, holds: bool, eligible: bool, expected) -> None:
    assert lifecycle_status(is_active=active, holds_position=holds, eligible=eligible) == expected


def test_has_position() -> None:
    bought = [_tx(TransactionKind.BUY, "10")]
    closed = [*bought, _tx(TransactionKind.SELL, "10")]
    assert has_position(bought, fixed_income=False)
    assert not has_position(closed, fixed_income=False)
    redeemed = [_tx(TransactionKind.BUY, "1", "1000"), _tx(TransactionKind.SELL, "1", "1100")]
    partial = [_tx(TransactionKind.BUY, "1", "1000"), _tx(TransactionKind.SELL, "1", "300")]
    assert not has_position(redeemed, fixed_income=True)
    assert has_position(partial, fixed_income=True)


def _stock(asset_id: int, ticker: str, answers: dict, *txs: TransactionEntity) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=AssetType.STOCK_BR,
        cerrado_answers=answers,
        transactions=txs,
    )


def test_contributions_skip_review_and_watchlist_assets() -> None:
    assets = [
        _stock(1, "GOOD3", GOOD, _tx(TransactionKind.BUY, "10")),
        _stock(2, "BAD3", BAD, _tx(TransactionKind.BUY, "10")),
        _stock(3, "NEW3", GOOD),
        _stock(4, "WATCH3", BAD),
    ]
    quotes = {a.ticker: Quote(a.ticker, 10.0) for a in assets}

    report = consolidate_portfolio(
        assets, ArcaTargets.default(), quotes=quotes, as_of_date=date(2025, 6, 30)
    )
    plan = plan_contribution(report, ArcaTargets.default(), 1000.0)

    status = {p.ticker: p.lifecycle_status for p in report.positions}
    assert status == {
        "GOOD3": AssetLifecycle.HELD,
        "BAD3": AssetLifecycle.REVIEW,
        "NEW3": AssetLifecycle.ELIGIBLE,
        "WATCH3": AssetLifecycle.WATCHLIST,
    }
    assert {o.ticker for o in plan.orders} == {"GOOD3", "NEW3"}


def test_strict_policy_turns_unevaluated_assets_into_watchlist() -> None:
    asset = _stock(1, "NEW3", {})
    report = consolidate_portfolio(
        [asset],
        ArcaTargets.default(),
        quotes={"NEW3": Quote("NEW3", 10.0)},
        eligibility=EligibilityPolicy(require_evaluation=True),
        as_of_date=date(2025, 6, 30),
    )
    assert report.positions[0].lifecycle_status == AssetLifecycle.WATCHLIST
    assert report.positions[0].eligible is False
