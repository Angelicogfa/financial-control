"""Use cases of the Garimpo (Phase 43): read what the worker stored."""

from __future__ import annotations

from controllers.research.responses import MiningMemberDTO, MiningUniverseDTO
from controllers.shared.dependencies import UoWFactory
from domain.mining.universe import MIN_DAILY_VOLUME, mining_universe
from domain.simulation.data import px_symbol


class MiningHandler:
    def __init__(self, uow_factory: UoWFactory, min_daily_volume: float = MIN_DAILY_VOLUME) -> None:
        self.uow_factory = uow_factory
        self.min_daily_volume = min_daily_volume

    def universe(self) -> MiningUniverseDTO:
        """The liquid stocks the mining looks at, and how far their stored history goes."""
        with self.uow_factory() as uow:
            members = mining_universe(uow, self.min_daily_volume)
            ranges = {m.ticker: uow.market_series.date_range(px_symbol(m.ticker)) for m in members}
            with_statements = uow.cvm_statements.cnpjs_with_statements()
        items = [
            MiningMemberDTO(
                ticker=m.ticker,
                company=m.company,
                sector=m.sector,
                daily_volume=m.daily_volume,
                volume_source=m.volume_source,  # type: ignore[arg-type]
                history_from=ranges[m.ticker][0] if ranges[m.ticker] else None,
                history_to=ranges[m.ticker][1] if ranges[m.ticker] else None,
                has_statements=m.cnpj in with_statements,
            )
            for m in members
        ]
        return MiningUniverseDTO(
            min_daily_volume=self.min_daily_volume,
            members=items,
            with_history=sum(1 for i in items if i.history_to is not None),
            with_statements=sum(1 for i in items if i.has_statements),
        )
