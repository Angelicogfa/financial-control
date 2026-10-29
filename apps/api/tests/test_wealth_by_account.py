"""Phase 40.2: wealth of each custody account, split into Bolsa and Internacional."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from domain.agentic.services.catalog import OPERATIONS
from domain.market.entities import Quote
from domain.policy.services.allocation import ClassAllocation
from domain.portfolio.services.market_split import market_groups
from domain.shared.entities import AccountEntity, AssetEntity, TransactionEntity
from domain.shared.enums import ArcaClass, AssetType, TransactionKind


def _allocation(arca: ArcaClass, value: float, invested: float, pnl: float) -> ClassAllocation:
    return ClassAllocation(
        arca_class=arca,
        label=arca.value,
        invested_value=invested,
        current_value=value,
        current_pct=0,
        target_pct=0,
        deviation_pct=0,
        gap_value=0,
        consolidated_pnl=pnl,
    )


def test_market_groups_put_caixa_acoes_and_real_estate_in_bolsa() -> None:
    b3, abroad = market_groups(
        [
            _allocation(ArcaClass.ACOES, 1200, 1000, 200),
            _allocation(ArcaClass.CAIXA, 500, 500, 0),
            _allocation(ArcaClass.REAL_ESTATE, 300, 400, -100),
            _allocation(ArcaClass.ATIVOS_INTERNACIONAIS, 900, 1000, -100),
        ]
    )
    assert (b3.label, b3.value, b3.invested, b3.pnl) == ("Bolsa", 2000, 1900, 100)
    assert b3.change == 100 / 1900
    assert (abroad.label, abroad.value, abroad.change) == ("Internacional", 900, -0.1)
    assert market_groups([])[0].change is None


def _buy(uow, asset: AssetEntity, account_id: int, qty: str) -> None:  # type: ignore[no-untyped-def]
    uow.transactions.add(
        TransactionEntity(
            asset_id=asset.id,
            kind=TransactionKind.BUY,
            trade_date=date(2026, 1, 5),
            quantity=Decimal(qty),
            unit_price=Decimal("10"),
            account_id=account_id,
        )
    )


def test_wealth_by_account_route(api: SimpleNamespace) -> None:
    now = datetime.now(UTC)
    with api.uow_factory() as uow:
        xp = uow.accounts.add(AccountEntity(name="XP", institution="XP Investimentos"))
        avenue = uow.accounts.add(AccountEntity(name="Avenue"))
        uow.accounts.add(AccountEntity(name="Vazia"))
        wege = uow.assets.add(
            AssetEntity(
                ticker="WEGE3",
                name="WEG",
                asset_type=AssetType.STOCK_BR,
                arca_class=ArcaClass.ACOES,
            )
        )
        ivvb = uow.assets.add(
            AssetEntity(
                ticker="IVVB11",
                name="S&P 500",
                asset_type=AssetType.ETF_BR,
                arca_class=ArcaClass.ATIVOS_INTERNACIONAIS,
            )
        )
        _buy(uow, wege, xp.id, "100")  # 1.000 invested -> 1.200
        _buy(uow, ivvb, xp.id, "10")  # 100 invested -> 90
        _buy(uow, ivvb, avenue.id, "50")  # 500 invested -> 450
        uow.market_data.save_quotes(
            {
                "WEGE3": Quote(symbol="WEGE3", price=12.0),
                "IVVB11": Quote(symbol="IVVB11", price=9.0),
            },
            fetched_at=now,
        )
        uow.commit()

    body = api.client.get("/api/v1/portfolio/by-account").json()
    names = [a["name"] for a in body["accounts"]]
    assert names == ["XP", "Avenue"]  # largest first; the empty account is left out
    xp_row = body["accounts"][0]
    assert xp_row["value_brl"] == 1290.0
    assert xp_row["share"] == 1290.0 / 1740.0
    groups = {g["label"]: g for g in xp_row["groups"]}
    assert groups["Bolsa"]["value_brl"] == 1200.0 and groups["Bolsa"]["change"] == 0.2
    assert groups["Internacional"]["value_brl"] == 90.0
    assert groups["Internacional"]["change"] == -0.1
    assert body["total_value_brl"] == 1740.0
    assert [g["label"] for g in body["groups"]] == ["Bolsa", "Internacional"]
    assert "portfolio.by_account" in {spec.name for spec in OPERATIONS}
