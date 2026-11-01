"""The mirrored flow (design 36, section 3): the money that entered or left the ARCA portfolio.

Only ARCA assets count (decision 10.1.7): the emergency reserve and the assets of purpose
"other" do not follow the policy. A purchase is money in, a sale is money out, both in BRL with
fees, the same rule the snapshots use for `net_flow`. Earnings are not external flow: every
comparison portfolio earns those of its own assets.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from domain.portfolio.services.snapshots import external_flow_brl
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, AssetPurpose, AssetType, TransactionKind


@dataclass(frozen=True)
class ActualTrade:
    """One real ARCA trade, kept to replay the real portfolio with the same prices."""

    day: date
    ticker: str
    arca_class: ArcaClass
    asset_type: AssetType
    amount: float  # BRL with fees: + bought, - sold
    quantity: float  # units bought (+) or sold (-)


def _arca(assets: Iterable[AssetEntity]) -> list[AssetEntity]:
    return [a for a in assets if a.purpose == AssetPurpose.ARCA and a.arca_class is not None]


def arca_flows(assets: Iterable[AssetEntity]) -> dict[date, float]:
    """Net ARCA flow of each day with trades (days that net to zero are dropped)."""
    out: dict[date, float] = {}
    for asset in _arca(assets):
        for tx in asset.transactions:
            if tx.kind not in (TransactionKind.BUY, TransactionKind.SELL):
                continue
            out[tx.trade_date] = out.get(tx.trade_date, 0.0) + external_flow_brl(tx)
    return {d: round(v, 2) for d, v in sorted(out.items()) if round(v, 2) != 0}


def arca_trades(assets: Iterable[AssetEntity]) -> list[ActualTrade]:
    """Every real ARCA purchase and sale, by date."""
    out = []
    for asset in _arca(assets):
        for tx in asset.transactions:
            if tx.kind not in (TransactionKind.BUY, TransactionKind.SELL):
                continue
            sign = 1.0 if tx.kind == TransactionKind.BUY else -1.0
            out.append(
                ActualTrade(
                    day=tx.trade_date,
                    ticker=asset.ticker.upper(),
                    arca_class=asset.arca_class,  # type: ignore[arg-type]
                    asset_type=asset.asset_type,
                    amount=round(external_flow_brl(tx), 2),
                    quantity=sign * float(tx.quantity),
                )
            )
    return sorted(out, key=lambda t: (t.day, t.ticker))
