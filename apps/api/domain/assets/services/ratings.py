"""Is each indicator good or not? A reading of the asset page's indicators.

Every rating says what it compared with, and the references are the strategy's own wherever it
has one, so the rating agrees with the valuation and the checklist of the same asset:

- P/L against the policy's maximum (15), P/VP against Graham (P/L x P/VP <= 22.5) for
  companies and against the policy's maximum for banks and funds;
- dividend yield against the yield the Bazin method requires (6%); a lower yield is a caution,
  never "bad": a company that reinvests can pay little;
- ROE above 10%, net debt / EBITDA below 2 and dividends in 80% of the years, as the checklist
  asks; the rest (margin, growth, payout, liquidity) with plain, stated references.

A value far outside what the indicator can be (a net margin above 100%, for instance) is
SUSPICIOUS rather than good or bad: it is usually a provider error and should be checked.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.assets.services.history import HistoricalMetrics
from domain.market.entities import Fundamentals
from domain.policy.services.policy import ValuationPolicy
from domain.shared.enums import ChecklistProfile

GOOD = "GOOD"
CAUTION = "CAUTION"
BAD = "BAD"
SUSPICIOUS = "SUSPICIOUS"

MIN_ROE = 0.10  # checklist (stocks)
WEAK_ROE = 0.05
MAX_NET_DEBT_TO_EBITDA = 2.0  # checklist
HIGH_NET_DEBT_TO_EBITDA = 3.0
GOOD_MARGIN = 0.10
DIVIDEND_REGULARITY = 0.8  # checklist
MIN_DAILY_VOLUME = 1_000_000.0  # the Garimpo's liquidity floor
MAX_PAYOUT = 1.0
FUNDS = {ChecklistProfile.FII_BRICK, ChecklistProfile.FII_PAPER}


@dataclass(frozen=True)
class IndicatorRating:
    status: str  # GOOD, CAUTION, BAD or SUSPICIOUS
    reference: str  # what it was compared with, in words


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%".replace(".", ",")


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _price_to_earnings(pe: float, policy: ValuationPolicy) -> IndicatorRating:
    limit = policy.max_price_to_earnings
    if pe <= 0:
        return IndicatorRating(BAD, "Lucro negativo nos últimos 12 meses.")
    if pe <= limit:
        return IndicatorRating(GOOD, f"Até {_num(limit, 0)}, o máximo da estratégia.")
    if pe <= 1.5 * limit:
        return IndicatorRating(CAUTION, f"Acima de {_num(limit, 0)}, o máximo da estratégia.")
    return IndicatorRating(BAD, f"Bem acima de {_num(limit, 0)}, o máximo da estratégia.")


def _price_to_book(
    pb: float, pe: float | None, profile: ChecklistProfile, policy: ValuationPolicy
) -> IndicatorRating:
    if pb <= 0:
        return IndicatorRating(BAD, "Patrimônio líquido negativo.")
    if profile == ChecklistProfile.BANK or profile in FUNDS:
        limit = (
            policy.max_price_to_book_bank
            if profile == ChecklistProfile.BANK
            else policy.max_price_to_book_fii
        )
        if pb <= limit:
            return IndicatorRating(GOOD, f"Até {_num(limit, 2)}, o máximo da estratégia.")
        if pb <= 1.25 * limit:
            return IndicatorRating(CAUTION, f"Acima de {_num(limit, 2)}, o máximo da estratégia.")
        return IndicatorRating(BAD, f"Bem acima de {_num(limit, 2)}, o máximo da estratégia.")
    if pe is None or pe <= 0:
        return IndicatorRating(CAUTION, "Sem lucro para o critério de Graham (P/L × P/VP).")
    graham = policy.graham_multiplier
    product = pe * pb
    if product <= graham:
        return IndicatorRating(GOOD, f"P/L × P/VP = {_num(product)}, até {_num(graham)} (Graham).")
    if product <= 1.5 * graham:
        return IndicatorRating(
            CAUTION, f"P/L × P/VP = {_num(product)}, acima de {_num(graham)} (Graham)."
        )
    return IndicatorRating(
        BAD, f"P/L × P/VP = {_num(product)}, bem acima de {_num(graham)} (Graham)."
    )


def rate_indicators(
    profile: ChecklistProfile,
    fund: Fundamentals | None,
    metrics: HistoricalMetrics | None,
    policy: ValuationPolicy,
) -> dict[str, IndicatorRating]:
    """Ratings by indicator key (the keys of the fundamentals and of the history)."""
    out: dict[str, IndicatorRating] = {}
    company = profile in (ChecklistProfile.STOCK, ChecklistProfile.INTL_STOCK)
    bank = profile == ChecklistProfile.BANK
    if fund is not None:
        pe, pb = fund.price_to_earnings, fund.price_to_book
        if pe is not None:
            out["price_to_earnings"] = _price_to_earnings(pe, policy)
        if pb is not None:
            out["price_to_book"] = _price_to_book(pb, pe, profile, policy)
        dy = fund.dividend_yield
        if dy is not None:
            required = policy.bazin_required_yield
            if dy > 0.5:
                out["dividend_yield"] = IndicatorRating(
                    SUSPICIOUS, "Acima de 50% ao ano: confira o dado."
                )
            elif dy >= required:
                out["dividend_yield"] = IndicatorRating(
                    GOOD, f"A partir de {_pct(required)} (Bazin)."
                )
            else:
                out["dividend_yield"] = IndicatorRating(
                    CAUTION,
                    f"Abaixo de {_pct(required)} (Bazin); empresa que reinveste pode pagar pouco.",
                )
        roe = fund.return_on_equity
        if roe is not None:
            out["return_on_equity"] = _roe(roe)
        margin = fund.profit_margin
        if margin is not None and (company or bank):
            if abs(margin) > 1.0:
                out["profit_margin"] = IndicatorRating(
                    SUSPICIOUS, "Fora do possível (acima de 100% da receita): confira o dado."
                )
            elif margin >= GOOD_MARGIN:
                out["profit_margin"] = IndicatorRating(GOOD, f"A partir de {_pct(GOOD_MARGIN)}.")
            elif margin > 0:
                out["profit_margin"] = IndicatorRating(
                    CAUTION, f"Positiva, abaixo de {_pct(GOOD_MARGIN)}."
                )
            else:
                out["profit_margin"] = IndicatorRating(BAD, "Prejuízo nos últimos 12 meses.")
        leverage = fund.net_debt_to_ebitda
        if leverage is not None and company:
            if leverage < 0:
                out["net_debt_to_ebitda"] = IndicatorRating(GOOD, "Caixa maior que a dívida.")
            elif leverage < MAX_NET_DEBT_TO_EBITDA:
                out["net_debt_to_ebitda"] = IndicatorRating(
                    GOOD, f"Abaixo de {_num(MAX_NET_DEBT_TO_EBITDA)}, como pede o checklist."
                )
            elif leverage < HIGH_NET_DEBT_TO_EBITDA:
                out["net_debt_to_ebitda"] = IndicatorRating(
                    CAUTION, f"Acima de {_num(MAX_NET_DEBT_TO_EBITDA)}, o limite do checklist."
                )
            else:
                out["net_debt_to_ebitda"] = IndicatorRating(
                    BAD,
                    f"A partir de {_num(HIGH_NET_DEBT_TO_EBITDA)}: dívida alta para o caixa.",
                )
        if fund.earnings_per_share is not None:
            out["earnings_per_share"] = (
                IndicatorRating(GOOD, "Lucro por ação positivo.")
                if fund.earnings_per_share > 0
                else IndicatorRating(BAD, "Prejuízo por ação.")
            )
        if fund.book_value_per_share is not None:
            out["book_value_per_share"] = (
                IndicatorRating(GOOD, "Patrimônio por ação positivo.")
                if fund.book_value_per_share > 0
                else IndicatorRating(BAD, "Patrimônio líquido negativo.")
            )
        volume = fund.avg_daily_volume
        if volume is not None:
            out["avg_daily_volume"] = (
                IndicatorRating(GOOD, "A partir de R$ 1 milhão por dia.")
                if volume >= MIN_DAILY_VOLUME
                else IndicatorRating(CAUTION, "Abaixo de R$ 1 milhão por dia: pouca liquidez.")
            )

    if metrics is not None and metrics.years > 0:
        if metrics.roe_average is not None:
            out["roe_average"] = _roe(metrics.roe_average)
        for key, value in (
            ("revenue_cagr", metrics.revenue_cagr),
            ("earnings_cagr", metrics.earnings_cagr),
        ):
            if value is not None:
                out[key] = (
                    IndicatorRating(GOOD, "Cresceu no período.")
                    if value > 0
                    else IndicatorRating(BAD, "Encolheu no período.")
                )
        share = metrics.profitable_years / metrics.years
        out["profitable_years"] = (
            IndicatorRating(GOOD, "Lucro em todos os anos.")
            if share == 1
            else IndicatorRating(CAUTION, "Prejuízo em algum ano.")
            if share >= DIVIDEND_REGULARITY
            else IndicatorRating(BAD, "Prejuízo em vários anos.")
        )
        regularity = metrics.dividend_regularity or 0.0
        out["dividend_years"] = (
            IndicatorRating(GOOD, f"Proventos em pelo menos {_pct(DIVIDEND_REGULARITY)} dos anos.")
            if regularity >= DIVIDEND_REGULARITY
            else IndicatorRating(
                CAUTION, f"Proventos em menos de {_pct(DIVIDEND_REGULARITY)} dos anos (checklist)."
            )
        )
        payout = metrics.payout_average
        if payout is not None:
            out["payout_average"] = (
                IndicatorRating(BAD, "Paga mais do que lucra.")
                if payout > MAX_PAYOUT
                else IndicatorRating(GOOD, "Paga com o próprio lucro.")
                if payout > 0
                else IndicatorRating(CAUTION, "Sem pagamento do lucro.")
            )
    return out


def _roe(value: float) -> IndicatorRating:
    if abs(value) > 1.5:
        return IndicatorRating(SUSPICIOUS, "Fora do comum (acima de 150%): confira o dado.")
    if value >= MIN_ROE:
        return IndicatorRating(GOOD, f"A partir de {_pct(MIN_ROE)}, como pede o checklist.")
    if value >= WEAK_ROE:
        return IndicatorRating(CAUTION, f"Abaixo de {_pct(MIN_ROE)}, o mínimo do checklist.")
    return IndicatorRating(BAD, f"Abaixo de {_pct(WEAK_ROE)}: retorno fraco sobre o patrimônio.")
