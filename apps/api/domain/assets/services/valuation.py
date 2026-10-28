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

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from statistics import median

from domain.assets.services.classic_valuation import (
    bazin_ceiling_price,
    graham_fair_value,
    margin_of_safety,
)
from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
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
    # Phase 25: inputs flagged as suspicious and one-off dividends in the trailing year.
    suspicious_inputs: tuple[str, ...] = ()
    extraordinary_dividends: bool = False


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


NORMALIZED_MIN_YEARS = 3
NORMALIZED_MAX_YEARS = 5
EXTRAORDINARY_RATIO = 1.5

# Indicators each method reads; a flagged one makes the method (and the verdict) suspicious.
METHOD_INPUTS: dict[str, tuple[str, ...]] = {
    "GRAHAM": ("price_to_earnings", "price_to_book"),
    "BAZIN": ("dividend_yield",),
    "PE": ("price_to_earnings",),
    "EV_EBITDA": (),
    "JUSTIFIED_PB": ("return_on_equity", "price_to_book"),
    "PB": ("price_to_book",),
    "DY": ("dividend_yield",),
    "SPREAD": ("dividend_yield",),
}


@dataclass(frozen=True)
class NormalizedDividends:
    """Median yearly dividends per share over 3-5 fiscal years (Phase 25.4)."""

    per_share: float
    years: int
    extraordinary: bool


def normalized_dividends(
    statements: Sequence[FundamentalSnapshot], price: float | None, f: Fundamentals
) -> NormalizedDividends | None:
    """Median of the dividends paid in the last 3-5 fiscal years, per share today.

    The share count is today's market cap / price. `extraordinary` marks trailing dividends
    above 1.5x the median (a one-off payment would inflate the Bazin ceiling).
    """
    if not price or price <= 0 or not f.market_cap:
        return None
    paid = [
        abs(s.value("dividends_paid") or 0.0)
        for s in sorted(
            (s for s in statements if s.period == FundamentalPeriod.ANNUAL),
            key=lambda s: s.reference_date,
            reverse=True,
        )
        if s.value("dividends_paid") is not None
    ][:NORMALIZED_MAX_YEARS]
    if len(paid) < NORMALIZED_MIN_YEARS:
        return None
    shares = f.market_cap / price
    per_share = median(paid) / shares
    if per_share <= 0:
        return None
    trailing = _dividends_per_share(price, f)
    return NormalizedDividends(
        per_share=per_share,
        years=len(paid),
        extraordinary=trailing is not None and trailing > EXTRAORDINARY_RATIO * per_share,
    )


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


def _bazin(
    price: float | None,
    f: Fundamentals,
    policy: ValuationPolicy,
    normalized: NormalizedDividends | None = None,
) -> MethodResult:
    if normalized is not None:
        fair = bazin_ceiling_price(normalized.per_share, policy.bazin_required_yield)
        note = f"Proventos normalizados: mediana de {normalized.years} anos"
        if normalized.extraordinary:
            note += "; os últimos 12 meses têm proventos extraordinários"
        return _price_method("BAZIN", "Preço teto de Bazin", fair, price, note=note)
    fair = bazin_ceiling_price(_dividends_per_share(price, f), policy.bazin_required_yield)
    return _price_method(
        "BAZIN", "Preço teto de Bazin", fair, price, note="Proventos dos últimos 12 meses"
    )


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
    statements: Sequence[FundamentalSnapshot] = (),
) -> AssetValuation:
    """Value an asset with the methods that fit its profile.

    With `statements`, Bazin uses the median dividends of 3-5 years instead of the
    trailing ones.
    """
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
    normalized = normalized_dividends(statements, price, f)
    if latest_statement is None and statements:
        latest_statement = max(statements, key=lambda s: s.reference_date)
    if profile == ChecklistProfile.STOCK:
        methods = [
            _graham(price, f, rules),
            _bazin(price, f, rules, normalized),
            _pe(f, rules),
            _ev_ebitda(f, latest_statement, rules),
        ]
    elif profile == ChecklistProfile.BANK:
        methods = [
            _bazin(price, f, rules, normalized),
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
    flagged = sorted(
        {
            field
            for m in methods
            for field in METHOD_INPUTS.get(m.method, ())
            if field in f.suspicious
        }
    )
    methods = [
        replace(m, note=(m.note + "; " if m.note else "") + "dado suspeito")
        if any(field in f.suspicious for field in METHOD_INPUTS.get(m.method, ()))
        else m
        for m in methods
    ]
    return AssetValuation(
        profile,
        True,
        price,
        tuple(methods),
        _round(fair_value),
        _round(margin, 4),
        verdict,
        suspicious_inputs=tuple(flagged),
        extraordinary_dividends=bool(normalized and normalized.extraordinary),
    )
