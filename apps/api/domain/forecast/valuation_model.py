"""Layer B of the price forecast: valuation in the prior of α (Phase 42.3).

Every month, each company gets four yields from the statements it had delivered by then and the
price of that month: earnings, book, EBITDA/EV and dividends over the market value (banks and
insurers: no EBITDA/EV). How cheap it is comes in two ways, averaged: against its own past
(time z, past months only) and against its sector that month (cross-sectional z, the sector
centre pulled to the market when the sector is small). The composite z is winsorised to ±3.

γ answers "a z of +1 was followed by how much more return than the class, a month, over the
next 12 months?". It is estimated by Fama-MacBeth (one slope per month, then their mean, with
the standard error widened for the overlap of the 12-month windows) and shrunk by a sceptical
prior N(0, τγ²). Sectors get their own slope pulled to the market one.

The gate is out of sample, by rolling origin: each year γ is estimated with what was known and
predicts the next year. Valuation enters the forecast only if it cut the squared error against
"no valuation" in total and in most years, and if the sign of γ is clear; otherwise γ = 0 and the
screen says so.

The market value of a past month is rebuilt as split-adjusted price x shares of the last
delivered statement x the splits after that statement (Yahoo adjusts the whole price history for
every split; the CVM reports the real share count of each date). With two share classes the
price of the traded one stands for both, as in most screeners.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.disclosures.statements import FINANCIAL, PitFundamentals
from domain.forecast.valuation_pit import valuation

Month = tuple[int, int]

YIELDS = ("earnings_yield", "book_yield", "ebitda_ev", "dividend_yield")
MIN_PAST_MONTHS = 24  # for the time z
MIN_COMPANIES = 10  # for a cross-section (z and the monthly slope)
SECTOR_PSEUDO_COUNT = 3.0  # how many "market" companies pull a sector's centre
MAX_STATEMENT_AGE_DAYS = 460  # a statement older than ~15 months is not used
WINSOR = 3.0
FORWARD_MONTHS = 12
PRIOR_SD = 0.002  # monthly α per z: ~2.4% a year, sceptical
SECTOR_PRIOR_SD = 0.001  # spread of the sector slopes around the market one
MIN_SECTOR_COMPANIES = 3
MIN_ORIGINS = 5
MIN_SIGN_PROBABILITY = 0.9
MIN_WIN_SHARE = 0.55


def month_of(day: date) -> Month:
    return (day.year, day.month)


def month_end(month: Month) -> date:
    year, m = month
    nxt = date(year + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def add_months(month: Month, n: int) -> Month:
    index = month[0] * 12 + (month[1] - 1) + n
    return (index // 12, index % 12 + 1)


# --- inputs and the monthly panel ------------------------------------------------------------


@dataclass(frozen=True)
class CompanyInput:
    ticker: str
    sector: str
    snapshots: Sequence[PitFundamentals]  # what was known after each delivery, oldest first
    prices: Mapping[Month, float]  # last split-adjusted price of each month
    splits: Sequence[tuple[date, float]] = ()  # (date, shares after / before)


def split_factor_after(splits: Sequence[tuple[date, float]], day: date) -> float:
    """Product of the split ratios after `day` (undoes Yahoo's adjustment back to `day`)."""
    factor = 1.0
    for when, ratio in splits:
        if when > day and ratio > 0:
            factor *= ratio
    return factor


def company_yields(company: CompanyInput) -> dict[Month, dict[str, float]]:
    """The yields of each month with a price and a recent enough delivered statement."""
    delivered = [s.delivered_on for s in company.snapshots]
    out: dict[Month, dict[str, float]] = {}
    for month, price in company.prices.items():
        end = month_end(month)
        i = bisect.bisect_right(delivered, end) - 1
        if i < 0 or price <= 0:
            continue
        snap = company.snapshots[i]
        if (end - snap.reference_date).days > MAX_STATEMENT_AGE_DAYS:
            continue
        found = valuation(snap, price * split_factor_after(company.splits, snap.reference_date))
        if found is None:
            continue
        values = {
            "earnings_yield": found.earnings_yield,
            "book_yield": (1.0 / found.price_to_book) if found.price_to_book else None,
            "ebitda_ev": (1.0 / found.ev_to_ebitda)
            if found.ev_to_ebitda and snap.template != FINANCIAL
            else None,
            "dividend_yield": found.dividend_yield,
        }
        clean = {k: v for k, v in values.items() if v is not None and math.isfinite(v)}
        if clean:
            out[month] = clean
    return out


def sector_z(row: Mapping[str, float], sectors: Mapping[str, str]) -> dict[str, float]:
    """z of each company against its sector in one cross-section (empty below MIN_COMPANIES).

    The sector centre is pulled to the market by SECTOR_PSEUDO_COUNT companies, so a sector of
    two does not define "cheap" by itself; the spread is the market's.
    """
    if len(row) < MIN_COMPANIES:
        return {}
    values = np.array(list(row.values()))
    market, spread = float(np.mean(values)), float(np.std(values, ddof=1))
    if spread <= 0:
        return {}
    by_sector: dict[str, list[float]] = defaultdict(list)
    for t, v in row.items():
        by_sector[sectors.get(t, "")].append(v)
    out = {}
    for t, v in row.items():
        peers = by_sector[sectors.get(t, "")]
        centre = (sum(peers) + SECTOR_PSEUDO_COUNT * market) / (len(peers) + SECTOR_PSEUDO_COUNT)
        out[t] = (v - centre) / spread
    return out


def value_scores(
    yields: Mapping[str, Mapping[Month, Mapping[str, float]]],
    sectors: Mapping[str, str],
) -> dict[str, dict[Month, float]]:
    """Composite z of each company and month: time z and sector z, averaged over the yields."""
    months = sorted({m for by_month in yields.values() for m in by_month})
    parts: dict[str, dict[Month, list[float]]] = defaultdict(lambda: defaultdict(list))

    # Against its own past (strictly earlier months).
    for ticker, by_month in yields.items():
        history: dict[str, list[float]] = defaultdict(list)
        for month in sorted(by_month):
            for name, value in by_month[month].items():
                past = history[name]
                if len(past) >= MIN_PAST_MONTHS:
                    sd = float(np.std(past, ddof=1))
                    if sd > 0:
                        parts[ticker][month].append((value - float(np.mean(past))) / sd)
                past.append(value)

    # Against its sector that month.
    for month in months:
        for name in YIELDS:
            row = {
                t: by_month[month][name]
                for t, by_month in yields.items()
                if month in by_month and name in by_month[month]
            }
            for t, z in sector_z(row, sectors).items():
                parts[t][month].append(z)

    return {
        t: {m: float(np.clip(np.mean(zs), -WINSOR, WINSOR)) for m, zs in by_month.items() if zs}
        for t, by_month in parts.items()
    }


def forward_alpha(
    monthly: Mapping[Month, float], horizon: int = FORWARD_MONTHS
) -> dict[Month, float]:
    """Mean monthly return over the class in the `horizon` months after each month."""
    out: dict[Month, float] = {}
    for month in monthly:
        ahead = [monthly.get(add_months(month, k)) for k in range(1, horizon + 1)]
        if all(v is not None for v in ahead):
            out[month] = float(np.mean(ahead))  # type: ignore[arg-type]
    return out


# --- estimation -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Slope:
    mean: float  # monthly α per unit of z
    se: float
    months: int


def _monthly_slopes(
    scores: Mapping[str, Mapping[Month, float]],
    forward: Mapping[str, Mapping[Month, float]],
    months: Sequence[Month],
    tickers: set[str] | None = None,
    min_obs: int = MIN_COMPANIES,
) -> list[float]:
    slopes = []
    for month in months:
        pairs = [
            (scores[t][month], forward[t][month])
            for t in scores
            if (tickers is None or t in tickers)
            and month in scores[t]
            and month in forward.get(t, {})
        ]
        if len(pairs) < min_obs:
            continue
        z = np.array([p[0] for p in pairs])
        y = np.array([p[1] for p in pairs])
        var = float(np.var(z))
        if var <= 0:
            continue
        slopes.append(float(np.mean((z - z.mean()) * (y - y.mean())) / var))
    return slopes


def fama_macbeth(slopes: Sequence[float], overlap: int = FORWARD_MONTHS) -> Slope | None:
    if len(slopes) < 2:
        return None
    effective = max(len(slopes) / overlap, 1.0)
    se = float(np.std(slopes, ddof=1)) / math.sqrt(effective)
    return Slope(float(np.mean(slopes)), max(se, 1e-9), len(slopes))


def posterior(slope: Slope, prior_mean: float, prior_sd: float) -> tuple[float, float]:
    """Normal-normal: (mean, sd)."""
    prec = 1.0 / prior_sd**2 + 1.0 / slope.se**2
    mean = (prior_mean / prior_sd**2 + slope.mean / slope.se**2) / prec
    return mean, math.sqrt(1.0 / prec)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class OriginResult:
    origin: str  # "2018-12"
    gamma: float
    mse_model: float
    mse_zero: float
    observations: int


@dataclass(frozen=True)
class ValuationModel:
    as_of: date
    gamma: float  # monthly α per z actually used (0 when the gate failed)
    gamma_estimate: float  # posterior mean before the gate
    gamma_sd: float
    sign_probability: float  # P(γ has the sign of its estimate)
    months: int  # monthly cross-sections used
    companies: int
    sectors: dict[str, float] = field(default_factory=dict)  # sector -> monthly γ used
    origins: list[OriginResult] = field(default_factory=list)
    oos_improvement: float = 0.0  # 1 - MSE(model) / MSE(zero), out of sample
    oos_win_share: float = 0.0  # share of years where the model won
    passed: bool = False
    reason: str = ""
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)  # ticker -> latest z

    def gamma_for(self, sector: str | None) -> float:
        if not self.passed:
            return 0.0
        return self.sectors.get(sector or "", self.gamma)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValuationModel:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["origins"] = [OriginResult(**o) for o in payload.get("origins", [])]
        return cls(**payload)


def _gate(
    scores: Mapping[str, Mapping[Month, float]],
    forward: Mapping[str, Mapping[Month, float]],
    months: Sequence[Month],
) -> list[OriginResult]:
    """Each December: γ from the months whose 12-month windows had closed; predict next year."""
    out: list[OriginResult] = []
    years = sorted({m[0] for m in months})
    for year in years:
        origin = (year, 12)
        train = [m for m in months if add_months(m, FORWARD_MONTHS) <= origin]
        test = [m for m in months if origin < m <= add_months(origin, 12)]
        slope = fama_macbeth(_monthly_slopes(scores, forward, train))
        if slope is None or slope.months < 24 or not test:
            continue
        gamma, _sd = posterior(slope, 0.0, PRIOR_SD)
        errors_model, errors_zero = [], []
        for t in scores:
            for m in test:
                if m in scores[t] and m in forward.get(t, {}):
                    y = forward[t][m]
                    errors_model.append((y - gamma * scores[t][m]) ** 2)
                    errors_zero.append(y**2)
        if len(errors_model) < MIN_COMPANIES:
            continue
        out.append(
            OriginResult(
                origin=f"{year}-12",
                gamma=gamma,
                mse_model=float(np.mean(errors_model)),
                mse_zero=float(np.mean(errors_zero)),
                observations=len(errors_model),
            )
        )
    return out


def estimate(
    scores: Mapping[str, Mapping[Month, float]],
    forward: Mapping[str, Mapping[Month, float]],
    sectors: Mapping[str, str],
    *,
    as_of: date,
) -> ValuationModel:
    """γ (global and by sector), the out-of-sample gate and the latest z of each company."""
    months = sorted({m for by_month in scores.values() for m in by_month})
    latest = {
        t: {"z": by_month[max(by_month)], "month": "{:04d}-{:02d}".format(*max(by_month))}
        for t, by_month in scores.items()
        if by_month
    }
    base = {"as_of": as_of, "companies": len(scores), "scores": latest}
    slope = fama_macbeth(_monthly_slopes(scores, forward, months))
    if slope is None:
        return ValuationModel(
            **base,
            gamma=0.0,
            gamma_estimate=0.0,
            gamma_sd=PRIOR_SD,
            sign_probability=0.5,
            months=0,
            reason="Poucos meses com empresas suficientes para medir o efeito do valuation.",
        )
    gamma, gamma_sd = posterior(slope, 0.0, PRIOR_SD)
    sign = _phi(abs(gamma) / gamma_sd)

    by_sector: dict[str, set[str]] = defaultdict(set)
    for t in scores:
        by_sector[sectors.get(t, "")].add(t)
    sector_gamma: dict[str, float] = {}
    for sector, tickers in by_sector.items():
        if not sector or len(tickers) < MIN_SECTOR_COMPANIES:
            continue
        own = fama_macbeth(
            _monthly_slopes(scores, forward, months, tickers, min_obs=MIN_SECTOR_COMPANIES)
        )
        if own is not None:
            sector_gamma[sector] = posterior(own, gamma, SECTOR_PRIOR_SD)[0]

    origins = _gate(scores, forward, months)
    mse_model = sum(o.mse_model * o.observations for o in origins)
    mse_zero = sum(o.mse_zero * o.observations for o in origins)
    improvement = 1.0 - mse_model / mse_zero if mse_zero > 0 else 0.0
    wins = sum(o.mse_model < o.mse_zero for o in origins)
    win_share = wins / len(origins) if origins else 0.0
    if len(origins) < MIN_ORIGINS:
        passed, reason = (
            False,
            f"Só {len(origins)} anos fora da amostra; são precisos {MIN_ORIGINS}.",
        )
    elif improvement <= 0 or win_share < MIN_WIN_SHARE:
        passed, reason = (
            False,
            f"Fora da amostra, o valuation não melhorou a previsão (erro {improvement:+.1%}, "
            f"ganhou em {wins} de {len(origins)} anos); não foi usado.",
        )
    elif sign < MIN_SIGN_PROBABILITY:
        passed, reason = (
            False,
            f"O sentido do efeito ainda é incerto ({sign:.0%} de confiança); não foi usado.",
        )
    else:
        passed, reason = (
            True,
            f"Fora da amostra, o valuation reduziu o erro em {improvement:.1%} e ganhou em "
            f"{wins} de {len(origins)} anos.",
        )
    return ValuationModel(
        **base,
        gamma=gamma if passed else 0.0,
        gamma_estimate=gamma,
        gamma_sd=gamma_sd,
        sign_probability=round(sign, 4),
        months=slope.months,
        sectors={s: g for s, g in sector_gamma.items()} if passed else {},
        origins=origins,
        oos_improvement=round(improvement, 6),
        oos_win_share=round(win_share, 4),
        passed=passed,
        reason=reason,
    )
