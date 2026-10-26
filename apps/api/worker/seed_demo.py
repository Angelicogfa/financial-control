"""Demonstration data: a reference-style portfolio with two years of history (item 14.1).

    uv run python -m fincontrol_worker.seed_demo            # DATABASE_URL from the env
    uv run python -m fincontrol_worker.seed_demo --years 1 --seed 7

Deterministic (seeded) and offline: prices, rates and indexes are synthetic, so the demo
works without market providers. It refuses to run on a database that already has assets —
it is meant for a fresh demo database, never for the real one.
"""

from __future__ import annotations

import argparse
import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from core.errors import ConflictError
from core.helpers.calendar import is_business_day
from domain.market.entities import Quote, QuoteFreshness
from domain.policy.services.policy import current_policy
from domain.portfolio.services.consolidation import consolidate_portfolio
from domain.portfolio.services.curves import earliest_fixed_income_start, load_rate_curves
from domain.portfolio.services.snapshots import net_flow_between, snapshot_from_report
from domain.shared.entities import (
    AccountEntity,
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from domain.shared.enums import (
    AccountKind,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    SeriesUnit,
    TransactionKind,
)
from domain.shared.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger("fincontrol_worker.seed_demo")
UoWFactory = Callable[[], AbstractUnitOfWork]

CDI_DAILY_PCT = 0.0525  # ~14% a year
IPCA_MONTHLY_PCT = 0.40
USD_BRL = 5.40


@dataclass(frozen=True)
class MarketSpec:
    ticker: str
    name: str
    asset_type: AssetType
    end_price: float
    annual_drift: float
    annual_vol: float
    monthly_budget: float
    annual_yield: float = 0.0
    payments_per_year: int = 0
    earning_kind: EarningKind = EarningKind.DIVIDEND
    currency_rate: float = 1.0
    profile: ChecklistProfile | None = None
    answers: dict[str, object] = field(default_factory=dict)


MARKET_ASSETS: tuple[MarketSpec, ...] = (
    MarketSpec(
        "WEGE3",
        "WEG S.A.",
        AssetType.STOCK_BR,
        52.0,
        0.12,
        0.28,
        600,
        0.015,
        4,
        answers={"innovation": True, "age_30y": True, "market_leader": True, "governance": True},
    ),
    MarketSpec(
        "ITSA4",
        "Itaúsa S.A.",
        AssetType.STOCK_BR,
        11.0,
        0.08,
        0.22,
        400,
        0.07,
        4,
        EarningKind.JCP,
        answers={"age_30y": True, "no_state_control": True},
    ),
    MarketSpec(
        "HGLG11",
        "CSHG Logística FII",
        AssetType.FII,
        160.0,
        0.02,
        0.12,
        500,
        0.09,
        12,
        EarningKind.FII_YIELD,
    ),
    MarketSpec(
        "KNCR11",
        "Kinea Rendimentos FII",
        AssetType.FII,
        105.0,
        0.0,
        0.06,
        300,
        0.12,
        12,
        EarningKind.FII_YIELD,
        profile=ChecklistProfile.FII_PAPER,
        answers={"high_grade": True},
    ),
    MarketSpec("IVVB11", "iShares S&P 500 FIC", AssetType.ETF_BR, 380.0, 0.14, 0.18, 300),
    MarketSpec(
        "VOO",
        "Vanguard S&P 500 ETF",
        AssetType.ETF_INTL,
        550.0,
        0.12,
        0.17,
        400,
        0.013,
        4,
        currency_rate=USD_BRL,
    ),
)

INDEXES: dict[str, tuple[float, float, float]] = {
    # symbol: (end level, drift, vol)
    "IBOV": (130_000.0, 0.08, 0.20),
    "IFIX": (3_300.0, 0.03, 0.08),
    "SP500": (5_800.0, 0.12, 0.16),
}


def _business_days(start: date, end: date) -> list[date]:
    days, current = [], start
    while current <= end:
        if is_business_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _price_path(rng: random.Random, days: int, end: float, drift: float, vol: float) -> list[float]:
    """Seeded geometric random walk rescaled to finish at `end`."""
    level, path = 1.0, []
    for _ in range(days):
        level *= math.exp(rng.gauss(drift / 252 - vol**2 / 504, vol / math.sqrt(252)))
        path.append(level)
    scale = end / path[-1]
    return [round(p * scale, 2) for p in path]


def _first_business_days(days: list[date]) -> list[date]:
    seen: set[tuple[int, int]] = set()
    firsts = []
    for d in days:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            firsts.append(d)
    return firsts


@dataclass
class DemoSummary:
    assets: int = 0
    trades: int = 0
    earnings: int = 0
    snapshots: int = 0
    first_day: date | None = None


def _write_series(
    uow: AbstractUnitOfWork, symbol: str, points: list[tuple[date, float]], unit: SeriesUnit
) -> None:
    """Synthetic series only where the database has none (never overwrites real data)."""
    if uow.market_series.date_range(symbol) is None:
        uow.market_series.upsert_points(symbol, points, unit=unit)


def seed_demo(
    uow_factory: UoWFactory,
    *,
    today: date | None = None,
    years: int = 2,
    seed: int = 42,
) -> DemoSummary:
    end = (today or date.today()) - timedelta(days=1)
    start = end - timedelta(days=365 * years)
    days = _business_days(start, end)
    rng = random.Random(seed)
    summary = DemoSummary(first_day=days[0])

    prices = {
        spec.ticker: dict(
            zip(
                days,
                _price_path(rng, len(days), spec.end_price, spec.annual_drift, spec.annual_vol),
                strict=True,
            )
        )
        for spec in MARKET_ASSETS
    }

    with uow_factory() as uow:
        if uow.assets.list_all(active_only=False):
            raise ConflictError(
                "The database already has assets: seed_demo only fills an empty demo database",
                code="DEMO_NOT_EMPTY",
            )
        account = uow.accounts.get_default() or uow.accounts.add(
            AccountEntity(name="Corretora Demo", institution="Demo", kind=AccountKind.BROKER)
        )
        account_id = account.id

        # Rates and indexes first: fixed income valuation reads them.
        _write_series(uow, "CDI", [(d, CDI_DAILY_PCT) for d in days], SeriesUnit.PERCENT_PER_DAY)
        _write_series(
            uow, "SELIC", [(d, CDI_DAILY_PCT + 0.0002) for d in days], SeriesUnit.PERCENT_PER_DAY
        )
        _write_series(
            uow,
            "IPCA",
            [(d, IPCA_MONTHLY_PCT) for d in _first_business_days(days)],
            SeriesUnit.PERCENT_PER_MONTH,
        )
        for symbol, (level, drift, vol) in INDEXES.items():
            path = _price_path(rng, len(days), level, drift, vol)
            _write_series(uow, symbol, list(zip(days, path, strict=True)), SeriesUnit.INDEX_POINTS)

        months = _first_business_days(days)
        for spec in MARKET_ASSETS:
            asset = uow.assets.add(
                AssetEntity(
                    ticker=spec.ticker,
                    name=spec.name,
                    asset_type=spec.asset_type,
                    checklist_profile=spec.profile,
                    cerrado_answers=spec.answers,
                )
            )
            summary.assets += 1
            held = Decimal("0")
            for index, day in enumerate(months):
                price = prices[spec.ticker][day]
                native = price
                fraction = spec.currency_rate != 1.0
                qty = Decimal(str(spec.monthly_budget / (price * spec.currency_rate)))
                qty = qty.quantize(
                    Decimal("0.0001") if fraction else Decimal("1"), rounding=ROUND_DOWN
                )
                if qty > 0:
                    uow.transactions.add(
                        TransactionEntity(
                            asset_id=asset.id or 0,
                            kind=TransactionKind.BUY,
                            trade_date=day,
                            quantity=qty,
                            unit_price=Decimal(str(native)),
                            fees=Decimal("0") if fraction else Decimal("4.90"),
                            fx_rate=Decimal(str(spec.currency_rate)),
                            account_id=account_id,
                            notes="Demonstração: aporte mensal",
                        )
                    )
                    held += qty
                    summary.trades += 1
                # One partial sale halfway through, to exercise realized results.
                if spec.ticker == "WEGE3" and index == len(months) // 2 and held > 10:
                    sold = (held * Decimal("0.2")).quantize(Decimal("1"), rounding=ROUND_DOWN)
                    uow.transactions.add(
                        TransactionEntity(
                            asset_id=asset.id or 0,
                            kind=TransactionKind.SELL,
                            trade_date=day + timedelta(days=1)
                            if is_business_day(day + timedelta(days=1))
                            else day,
                            quantity=sold,
                            unit_price=Decimal(str(round(price * 1.01, 2))),
                            fees=Decimal("4.90"),
                            account_id=account_id,
                            notes="Demonstração: realização parcial",
                        )
                    )
                    held -= sold
                    summary.trades += 1
                pays = (
                    spec.payments_per_year
                    and index > 0
                    and (index * spec.payments_per_year) % 12 == 0
                )
                if pays and held > 0:
                    gross = Decimal(
                        str(
                            round(
                                float(held) * price * spec.annual_yield / spec.payments_per_year, 2
                            )
                        )
                    )
                    if gross > 0:
                        tax = (
                            (gross * Decimal("0.15")).quantize(Decimal("0.01"))
                            if spec.earning_kind == EarningKind.JCP
                            else Decimal("0")
                        )
                        uow.earnings.add(
                            EarningEntity(
                                asset_id=asset.id or 0,
                                kind=spec.earning_kind,
                                payment_date=day + timedelta(days=14),
                                gross_amount=gross,
                                withholding_tax=tax,
                                fx_rate=Decimal(str(spec.currency_rate)),
                                account_id=account_id,
                            )
                        )
                        summary.earnings += 1

        fixed_income = (
            (
                "CDB 110% CDI",
                AssetType.FIXED_INCOME,
                FixedIncomeInstrumentKind.CDB,
                FixedIncomeIndexer.CDI,
                "1.10",
                days[0],
                "10000",
                False,
            ),
            (
                "LCI 95% CDI",
                AssetType.FIXED_INCOME,
                FixedIncomeInstrumentKind.LCI,
                FixedIncomeIndexer.CDI,
                "0.95",
                days[len(days) // 2],
                "5000",
                True,
            ),
            (
                "Tesouro IPCA+ 2035",
                AssetType.TREASURY,
                FixedIncomeInstrumentKind.TESOURO_IPCA,
                FixedIncomeIndexer.IPCA,
                "0.065",
                days[len(days) // 4],
                "4000",
                False,
            ),
        )
        for index, (name, kind, instrument, indexer, rate, issue, amount, exempt) in enumerate(
            fixed_income
        ):
            asset = uow.assets.add(
                AssetEntity(
                    ticker=f"DEMO-RF{index + 1}",
                    name=name,
                    asset_type=kind,
                    fixed_income_term=FixedIncomeTermEntity(
                        instrument_kind=instrument,
                        indexer=indexer,
                        contracted_rate=Decimal(rate),
                        issue_date=issue,
                        maturity_date=end + timedelta(days=365 * 3),
                        tax_exempt=exempt,
                    ),
                )
            )
            uow.transactions.add(
                TransactionEntity(
                    asset_id=asset.id or 0,
                    kind=TransactionKind.BUY,
                    trade_date=issue,
                    quantity=Decimal("1"),
                    unit_price=Decimal(amount),
                    account_id=account_id,
                )
            )
            summary.assets += 1
            summary.trades += 1

        reserve = uow.assets.add(
            AssetEntity(
                ticker="DEMO-RESERVA",
                name="Reserva de emergência",
                asset_type=AssetType.CASH,
                purpose=AssetPurpose.EMERGENCY_RESERVE,
                manual_price=Decimal("1"),
            )
        )
        uow.transactions.add(
            TransactionEntity(
                asset_id=reserve.id or 0,
                kind=TransactionKind.BUY,
                trade_date=days[0],
                quantity=Decimal("8000"),
                unit_price=Decimal("1"),
                account_id=account_id,
            )
        )
        summary.assets += 1
        summary.trades += 1
        uow.commit()

    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)
        policy = current_policy(uow.policies)
        curves = load_rate_curves(
            uow.market_series,
            date_from=earliest_fixed_income_start(assets),
            date_to=end,
            annual_cdi_rate=0.14,
            annual_ipca_rate=0.048,
        )
        previous: date | None = None
        for day in days:
            quotes = {
                spec.ticker: Quote(
                    symbol=spec.ticker,
                    price=prices[spec.ticker][day],
                    freshness=QuoteFreshness.CACHED,
                )
                for spec in MARKET_ASSETS
            }
            report = consolidate_portfolio(
                assets,
                policy.arca.targets,
                quotes=quotes,
                intra_strategies=policy.arca.strategies,
                bands=policy.arca.bands,
                eligibility=policy.eligibility,
                usd_brl_rate=USD_BRL,
                curves=curves,
                assumptions=policy.valuation.projections,
                as_of_date=day,
            )
            if report.total_invested_brl <= 0:
                continue
            uow.snapshots.upsert(
                snapshot_from_report(
                    report, net_flow=net_flow_between(assets, after=previous, up_to=day)
                )
            )
            previous = day
            summary.snapshots += 1
        uow.commit()
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fill an EMPTY database with demonstration data.")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    from infra.data.unit_of_work import SqlAlchemyUnitOfWork

    summary = seed_demo(SqlAlchemyUnitOfWork, today=args.today, years=args.years, seed=args.seed)
    print(
        f"Demo ready: {summary.assets} assets, {summary.trades} trades, "
        f"{summary.earnings} earnings, {summary.snapshots} daily snapshots "
        f"since {summary.first_day}."
    )


if __name__ == "__main__":
    main()
