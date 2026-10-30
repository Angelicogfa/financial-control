"""The mining universe (Phase 43.1): liquid Brazilian stocks with statements at the CVM.

- Candidates are the catalog's Brazilian stocks (the daily B3 list, Phase 11.6).
- A company needs a trading code in the CVM map, so its statements can be read (42.2).
- Liquidity is the average daily financial volume from the stored indicators (Phase 39.5),
  or the last session's volume while the indicators are missing; the floor is R$ 1 million a
  day (decision 43.0-1).
- One share class per company: the most liquid one stands for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.disclosures.services.sync import base_ticker
from domain.shared.enums import AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork

MIN_DAILY_VOLUME = 1_000_000.0  # decision 43.0-1
MAX_FINDINGS = 10  # a week, decision 43.0-2


@dataclass(frozen=True)
class MiningMember:
    ticker: str
    cnpj: str
    company: str
    sector: str
    daily_volume: float
    volume_source: str  # AVERAGE (stored indicators) or LAST_SESSION (catalog)


def mining_universe(
    uow: AbstractUnitOfWork, min_daily_volume: float = MIN_DAILY_VOLUME
) -> list[MiningMember]:
    """Liquid Brazilian stocks with a CNPJ in the CVM map, most liquid first."""
    stocks = [i for i in uow.catalog.list_all() if i.asset_type == AssetType.STOCK_BR]
    if not stocks:
        return []
    cnpjs = uow.cvm_issuers.cnpjs_for([base_ticker(i.ticker) for i in stocks])
    stored = uow.market_data.get_many(i.ticker for i in stocks)
    best: dict[str, MiningMember] = {}
    for item in stocks:
        cnpj = cnpjs.get(base_ticker(item.ticker))
        if cnpj is None:
            continue
        data = stored.get(item.ticker.upper())
        average = data.fundamentals.avg_daily_volume if data and data.fundamentals else None
        volume, source = (
            (average, "AVERAGE") if average else (item.volume_brl or 0.0, "LAST_SESSION")
        )
        if volume < min_daily_volume:
            continue
        member = MiningMember(
            ticker=item.ticker.upper(),
            cnpj=cnpj,
            company=item.name,
            sector=item.sector or "",
            daily_volume=float(volume),
            volume_source=source,
        )
        current = best.get(cnpj)
        if current is None or member.daily_volume > current.daily_volume:
            best[cnpj] = member
    return sorted(best.values(), key=lambda m: -m.daily_volume)
