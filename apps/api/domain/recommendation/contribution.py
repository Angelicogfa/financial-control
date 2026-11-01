"""The contribution the recommendation would make, next to the current one (Phase 45.4).

The class budget is the current rule's (ARCA bands and deficit, design N1 unchanged). Inside the
class, the target weights are the construction (45.4) pulled toward the current weights by the
confidence; the money goes first to who is furthest below the target (no sale), in whole units
for the types traded in lots, skipping a purchase below the minimum lot. Nothing is saved: the
switch of the contribution to these targets is Phase 45.6.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from domain.policy.services.allocation import distribute_by_targets
from domain.recommendation.construction import ClassConstruction, pulled_targets


@dataclass(frozen=True)
class RecommendedOrder:
    ticker: str
    target_weight: float  # inside the class, after the pull toward the current weights
    current_weight: float
    amount: float  # spent
    quantity: float
    unit_price: float | None
    reason: str


@dataclass(frozen=True)
class RecommendedClass:
    orders: list[RecommendedOrder]
    leftover: float


def recommended_orders(
    budget: float,
    construction: ClassConstruction,
    current_values: Mapping[str, float],
    prices: Mapping[str, float],
    whole_units: Mapping[str, bool],
    min_lot: float,
) -> RecommendedClass:
    """Spend the class budget toward the recommended targets."""
    targets = pulled_targets(construction, current_values)
    held = sum(v for v in current_values.values() if v > 0)
    allocation = distribute_by_targets(
        {t: max(current_values.get(t, 0.0), 0.0) for t in targets}, targets, max(budget, 0.0)
    )
    reasons = {s.ticker: s.reason for s in construction.selected}
    plans: dict[str, dict] = {}
    leftover = 0.0
    for ticker in sorted(targets, key=lambda t: -allocation.get(t, 0.0)):
        amount = allocation.get(ticker, 0.0)
        price = prices.get(ticker)
        plan = {"quantity": 0.0, "spent": 0.0, "reason": reasons.get(ticker, "")}
        if amount <= 0:
            plan["reason"] = (
                "Já está no peso-alvo ou acima."
                if ticker in reasons
                else "Mantido pelo peso atual, mas fora da escolha da recomendação."
            )
        elif price is None or price <= 0:
            plan["reason"] = "Sem preço guardado para calcular a quantidade."
            leftover += amount
        elif amount < min_lot:
            plan["reason"] = f"Valor abaixo do lote mínimo de R$ {min_lot:,.0f}.".replace(",", ".")
            leftover += amount
        else:
            units = (
                math.floor(amount / price + 1e-9)
                if whole_units.get(ticker, True)
                else amount / price
            )
            plan["quantity"], plan["spent"] = units, units * price
            leftover += amount - units * price
        plans[ticker] = plan
    # Leftovers buy whole units of the largest targets first, while they reach.
    for ticker in sorted(targets, key=lambda t: -targets[t]):
        price = prices.get(ticker)
        if not price or price <= 0 or price > leftover or plans[ticker]["spent"] <= 0:
            continue
        extra = math.floor(leftover / price + 1e-9) if whole_units.get(ticker, True) else 0
        if extra:
            plans[ticker]["quantity"] += extra
            plans[ticker]["spent"] += extra * price
            leftover -= extra * price
    orders = [
        RecommendedOrder(
            ticker=ticker,
            target_weight=round(targets[ticker], 6),
            current_weight=round(current_values.get(ticker, 0.0) / held, 6) if held > 0 else 0.0,
            amount=round(plan["spent"], 2),
            quantity=round(plan["quantity"], 6),
            unit_price=prices.get(ticker),
            reason=plan["reason"],
        )
        for ticker, plan in sorted(plans.items(), key=lambda kv: -targets[kv[0]])
    ]
    return RecommendedClass(orders, round(leftover, 2))
