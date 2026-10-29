"""Wealth split between what trades in Brazil and abroad (Phase 37.7 and 40.2).

Bolsa groups the ARCA classes held through the Brazilian market (Caixa, Ações and Real
Estate); Internacional is the international class. Each group carries its result over what
was invested, so a screen can say whether it is up or down.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from domain.policy.services.allocation import ClassAllocation
from domain.shared.enums import ArcaClass

B3_CLASSES = frozenset({ArcaClass.CAIXA, ArcaClass.ACOES, ArcaClass.REAL_ESTATE})
GROUP_LABELS = {"B3": "Bolsa", "INTERNATIONAL": "Internacional"}


@dataclass(frozen=True)
class MarketGroup:
    key: str
    label: str
    value: float
    invested: float
    pnl: float

    @property
    def change(self) -> float | None:
        """Consolidated result over the invested amount; None when nothing was invested."""
        return self.pnl / self.invested if self.invested > 0 else None


def market_groups(allocations: Iterable[ClassAllocation]) -> list[MarketGroup]:
    """Bolsa and Internacional, always in this order (zeros when a group is empty)."""
    items = list(allocations)
    groups = []
    for key, inside in (("B3", True), ("INTERNATIONAL", False)):
        chosen = [a for a in items if (a.arca_class in B3_CLASSES) == inside]
        groups.append(
            MarketGroup(
                key=key,
                label=GROUP_LABELS[key],
                value=round(sum(a.current_value for a in chosen), 2),
                invested=round(sum(a.invested_value for a in chosen), 2),
                pnl=round(sum(a.consolidated_pnl for a in chosen), 2),
            )
        )
    return groups
