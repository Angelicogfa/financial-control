"""Valuation by instrument profile (item 11.5).

- STOCK: Graham and Bazin fair prices, P/L and EV/EBITDA against policy ceilings.
- BANK: Bazin, P/VP and the justified P/VP (ROE / cost of equity) fair price.
- FII_BRICK / FII_PAPER: P/VP, dividend yield and its spread over the reference real yield
  (NTN-B), since FII income is exempt and competes with inflation-linked bonds.
- INTL_STOCK: Graham, P/L and EV/EBITDA (no Bazin: payout policies differ abroad).
- ETF, CRYPTO, FIXED_INCOME: not applicable; there is no intrinsic value to estimate.

Fair-price methods (kind PRICE) are combined by their median; multiples and yields
(MULTIPLE, YIELD) pass or fail against the policy thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from statistics import median

from domain.assets.services.classic_valuation import (
    bazin_ceiling_price,
    graham_fair_value,
    margin_of_safety,
)
from domain.assets.services.history import FundamentalSnapshot
from domain.market.entities import Fundamentals
from domain.policy.services.policy import ValuationPolicy
from domain.shared.enums import ChecklistProfile


class MethodKind(StrEnum):
    PRICE = "PRICE"
    MULTIPLE = "MULTIPLE"
    YIELD = "YIELD"


class ValuationVerdict(StrEnum):
    DISCOUNTED = "DISCOUNTED"
    FAIR = "FAIR"
    EXPENSIVE = "EXPENSIVE"
    UNDEFINED = "UNDEFINED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class MethodResult:
    """One valuation lens: a fair price (PRICE) or a metric checked against a threshold."""

    method: str
    label: str
    kind: MethodKind
    value: float | None
    threshold: float | None = None
    passes: bool | None = None
    margin: float | None = None
    note: str = ""


@dataclass(frozen=True)
class AssetValuation:
    profile: ChecklistProfile
    applicable: bool
    price: float | None
    methods: tuple[MethodResult, ...]
    fair_value: float | None
    margin: float | None
    verdict: ValuationVerdict
    reason: str = ""


NOT_APPLICABLE_REASONS: dict[ChecklistProfile, str] = {
    ChecklistProfile.ETF: "ETFs replicam índices; avalie custo, aderência e liquidez.",
    ChecklistProfile.CRYPTO: "Criptoativos não geram fluxo de caixa para descontar.",
    ChecklistProfile.FIXED_INCOME: "Renda fixa é avaliada pela taxa contratada e pelo emissor.",
}


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _price_method(
    method: str, label: str, fair: float | None, price: float | None, note: str = ""
) -> MethodResult:
    margin = margin_of_safety(fair, price)
    return MethodResult(
        method,
        label,
        MethodKind.PRICE,
        _round(fair),
        passes=None if margin is None else margin >= 0,
        margin=_round(margin, 4),
        note=note,
    )


def _ceiling(
    method: str, label: str, value: float | None, ceiling: float, kind: MethodKind
) -> MethodResult:
    if value is None or value <= 0:
        return MethodResult(method, label, kind, None, ceiling, None, note="Sem dado ou negativo")
    return MethodResult(method, label, kind, _round(value, 4), ceiling, value <= ceiling)


def _floor(
    method: str, label: str, value: float | None, floor: float, kind: MethodKind
) -> MethodResult:
    if value is None:
        return MethodResult(method, label, kind, None, floor, None, note="Sem dado")
    return MethodResult(method, label, kind, _round(value, 4), floor, value >= floor)


def _dividends_per_share(price: float | None, f: Fundamentals) -> float | None:
    if f.dividends_per_share_ttm is not None:
        return f.dividends_per_share_ttm
    if f.dividend_yield is not None and price:
        return f.dividend_yield * price
    return None


def ev_to_ebitda(f: Fundamentals, statement: FundamentalSnapshot | None) -> float | None:
    """EV/EBITDA from market cap and the latest yearly statement."""
    if statement is None or f.market_cap is None:
        return None
    ebitda = statement.value("ebitda")
    if ebitda is None or ebitda <= 0:
        return None
    debt = statement.value("total_debt") or 0.0
    cash = statement.value("cash") or 0.0
    return (f.market_cap + debt - cash) / ebitda


def _graham(price: float | None, f: Fundamentals, policy: ValuationPolicy) -> MethodResult:
    fair = graham_fair_value(f.earnings_per_share, f.book_value_per_share, policy.graham_multiplier)
    return _price_method("GRAHAM", "Preço justo de Graham", fair, price)


def _bazin(price: float | None, f: Fundamentals, policy: ValuationPolicy) -> MethodResult:
    fair = bazin_ceiling_price(_dividends_per_share(price, f), policy.bazin_required_yield)
    return _price_method("BAZIN", "Preço teto de Bazin", fair, price)


def _pe(f: Fundamentals, policy: ValuationPolicy) -> MethodResult:
    return _ceiling(
        "PE", "P/L", f.price_to_earnings, policy.max_price_to_earnings, MethodKind.MULTIPLE
    )


def _ev_ebitda(
    f: Fundamentals, statement: FundamentalSnapshot | None, policy: ValuationPolicy
) -> MethodResult:
    return _ceiling(
        "EV_EBITDA",
        "EV/EBITDA",
        ev_to_ebitda(f, statement),
        policy.max_ev_to_ebitda,
        MethodKind.MULTIPLE,
    )


def _justified_pb(price: float | None, f: Fundamentals, policy: ValuationPolicy) -> MethodResult:
    fair = None
    if f.return_on_equity and f.return_on_equity > 0 and f.book_value_per_share:
        fair = f.book_value_per_share * f.return_on_equity / policy.bank_cost_of_equity
    return _price_method(
        "JUSTIFIED_PB",
        "P/VP justificado (ROE / custo de capital)",
        fair,
        price,
        note=f"Custo de capital {policy.bank_cost_of_equity:.1%}",
    )


def _fii_methods(f: Fundamentals, policy: ValuationPolicy) -> list[MethodResult]:
    spread = (
        f.dividend_yield - policy.reference_real_yield if f.dividend_yield is not None else None
    )
    return [
        _ceiling("PB", "P/VP", f.price_to_book, policy.max_price_to_book_fii, MethodKind.MULTIPLE),
        _floor(
            "DY",
            "Dividend yield 12m",
            f.dividend_yield,
            policy.bazin_required_yield,
            MethodKind.YIELD,
        ),
        replace(
            _floor(
                "SPREAD",
                "Spread do DY sobre o juro real de referência",
                spread,
                policy.min_fii_spread,
                MethodKind.YIELD,
            ),
            note=f"Juro real de referência (NTN-B) {policy.reference_real_yield:.2%}",
        ),
    ]


def value_asset(
    profile: ChecklistProfile,
    price: float | None,
    fundamentals: Fundamentals | None,
    policy: ValuationPolicy | None = None,
    *,
    latest_statement: FundamentalSnapshot | None = None,
) -> AssetValuation:
    """Value an asset with the methods that fit its profile."""
    rules = policy or ValuationPolicy()
    if profile in NOT_APPLICABLE_REASONS:
        return AssetValuation(
            profile,
            False,
            price,
            (),
            None,
            None,
            ValuationVerdict.NOT_APPLICABLE,
            NOT_APPLICABLE_REASONS[profile],
        )
    if fundamentals is None:
        return AssetValuation(
            profile, True, price, (), None, None, ValuationVerdict.UNDEFINED, "Sem fundamentos"
        )

    f = fundamentals
    if profile == ChecklistProfile.STOCK:
        methods = [
            _graham(price, f, rules),
            _bazin(price, f, rules),
            _pe(f, rules),
            _ev_ebitda(f, latest_statement, rules),
        ]
    elif profile == ChecklistProfile.BANK:
        methods = [
            _bazin(price, f, rules),
            _justified_pb(price, f, rules),
            _ceiling(
                "PB", "P/VP", f.price_to_book, rules.max_price_to_book_bank, MethodKind.MULTIPLE
            ),
        ]
    elif profile in (ChecklistProfile.FII_BRICK, ChecklistProfile.FII_PAPER):
        methods = _fii_methods(f, rules)
    else:  # INTL_STOCK
        methods = [
            _graham(price, f, rules),
            _pe(f, rules),
            _ev_ebitda(f, latest_statement, rules),
        ]

    fair_prices = [m.value for m in methods if m.kind == MethodKind.PRICE and m.value]
    fair_value = median(fair_prices) if fair_prices else None
    margin = margin_of_safety(fair_value, price)
    if margin is not None:
        if margin >= rules.min_margin_of_safety:
            verdict = ValuationVerdict.DISCOUNTED
        elif margin >= 0:
            verdict = ValuationVerdict.FAIR
        else:
            verdict = ValuationVerdict.EXPENSIVE
    else:
        checks = [m.passes for m in methods if m.passes is not None]
        if not checks:
            verdict = ValuationVerdict.UNDEFINED
        elif all(checks):
            verdict = ValuationVerdict.DISCOUNTED
        elif any(checks):
            verdict = ValuationVerdict.FAIR
        else:
            verdict = ValuationVerdict.EXPENSIVE
    return AssetValuation(
        profile,
        True,
        price,
        tuple(methods),
        _round(fair_value),
        _round(margin, 4),
        verdict,
    )
