"""Reading an alert rule against what the database has (Phase 48.R6). Pure.

No provider is called: the price is the last stored quote (or the close of the B3 catalog),
the ratios are the stored fundamentals. A rule without data never fires.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

from domain.market.entities import StoredMarketData
from domain.shared.entities import CatalogInstrument
from domain.watch.entities import METRIC_LABELS, AlertRule, RuleMetric, RuleOperator, RuleReading


def metric_value(
    metric: RuleMetric,
    stored: StoredMarketData | None,
    catalog: CatalogInstrument | None,
) -> float | None:
    if metric == RuleMetric.PRICE:
        if stored is not None and stored.quote is not None and stored.quote.price > 0:
            return stored.quote.price
        return catalog.close if catalog is not None and catalog.close else None
    f = stored.fundamentals if stored is not None else None
    if f is None:
        return None
    return {
        RuleMetric.DIVIDEND_YIELD: f.dividend_yield,
        RuleMetric.PRICE_TO_EARNINGS: f.price_to_earnings,
        RuleMetric.PRICE_TO_BOOK: f.price_to_book,
    }[metric]


def holds(rule: AlertRule, value: float | None) -> bool:
    if value is None:
        return False
    threshold = float(rule.threshold)
    return value >= threshold if rule.operator == RuleOperator.ABOVE else value <= threshold


def read_rules(
    rules: Iterable[AlertRule],
    stored: Mapping[str, StoredMarketData],
    catalog: Mapping[str, CatalogInstrument],
) -> list[RuleReading]:
    readings = []
    for rule in rules:
        value = metric_value(rule.metric, stored.get(rule.ticker), catalog.get(rule.ticker))
        readings.append(
            RuleReading(rule=rule, value=value, triggered=rule.is_active and holds(rule, value))
        )
    return readings


def _number(metric: RuleMetric, value: float | Decimal) -> str:
    v = float(value)
    if metric == RuleMetric.DIVIDEND_YIELD:
        return f"{v * 100:.2f}%".replace(".", ",")
    if metric == RuleMetric.PRICE:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:.2f}".replace(".", ",")


def describe(rule: AlertRule) -> str:
    """'Preço de PETR4 abaixo de R$ 30,00' (user-facing, pt-BR)."""
    side = "acima de" if rule.operator == RuleOperator.ABOVE else "abaixo de"
    limit = _number(rule.metric, rule.threshold)
    return f"{METRIC_LABELS[rule.metric]} de {rule.ticker} {side} {limit}"


def reading_detail(reading: RuleReading) -> str:
    if reading.value is None:
        return "Sem dado guardado para conferir a regra."
    return f"Agora: {_number(reading.rule.metric, reading.value)}."
