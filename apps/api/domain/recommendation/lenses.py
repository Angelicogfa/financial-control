"""The lenses of the recommendation (Phase 45.1, design N4): what the data say about each asset.

Every lens answers one question and gives, per asset, a value, the value on [0, 1] for the
decision matrix (higher is always better), a confidence and a sentence. A lens without data has
no value: the combination (45.3) decides what a missing lens is worth.

- L0 CERRADO: your qualitative analysis on an absolute 0-10 scale. Not analysed scores 0 (the
  asset still competes, with a highlight); a partial analysis is the full score times the
  coverage; a stale answer loses weight linearly until 12 months after it expired. A checklist
  switched off for the asset takes the lens out of its score.
- L1 QUALITY, L2 VALUATION, L3 IMPROVEMENT, L4 MOMENTUM, L5 INCOME, L6 RISK: the latest month of
  the point-in-time panel, each a z against the sector winsorised to ±3 (RISK flipped: a high z
  is a low risk).
- L7 PROJECTION: the price forecast's expected return over the class with the market and event
  layers only. Valuation (layer B) is left out because it already is L2 (decision 10.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from domain.assets.services.cerrado import CerradoEvaluation
from domain.mining.signals import IMPROVEMENT as SIGNAL_IMPROVEMENT
from domain.mining.signals import MOMENTUM as SIGNAL_MOMENTUM
from domain.mining.signals import QUALITY as SIGNAL_QUALITY
from domain.mining.signals import VALUE as SIGNAL_VALUE
from domain.recommendation.signals import INCOME as SIGNAL_INCOME
from domain.recommendation.signals import RISK as SIGNAL_RISK

CERRADO = "CERRADO"
QUALITY = "QUALITY"
VALUATION = "VALUATION"
IMPROVEMENT = "IMPROVEMENT"
MOMENTUM = "MOMENTUM"
INCOME = "INCOME"
RISK = "RISK"
PROJECTION = "PROJECTION"
LENSES = (CERRADO, QUALITY, VALUATION, IMPROVEMENT, MOMENTUM, INCOME, RISK, PROJECTION)

LENS_LABELS = {
    CERRADO: "Cerrado",
    QUALITY: "Qualidade",
    VALUATION: "Valuation",
    IMPROVEMENT: "Melhora",
    MOMENTUM: "Momentum",
    INCOME: "Renda",
    RISK: "Risco",
    PROJECTION: "Projeção",
}

# Lens -> signal of the point-in-time panel.
LENS_SIGNALS = {
    QUALITY: SIGNAL_QUALITY,
    VALUATION: SIGNAL_VALUE,
    IMPROVEMENT: SIGNAL_IMPROVEMENT,
    MOMENTUM: SIGNAL_MOMENTUM,
    INCOME: SIGNAL_INCOME,
    RISK: SIGNAL_RISK,
}

# Where the asset comes from (design N2): all three compete (decision 10.4).
PORTFOLIO = "PORTFOLIO"
WATCHLIST = "WATCHLIST"
CATALOG = "CATALOG"

# Highlights the screens show next to the score.
NOT_ANALYZED = "NOT_ANALYZED"
PARTIAL = "PARTIAL"
STALE = "STALE"
CERRADO_OFF = "CERRADO_OFF"

WINSOR = 3.0
CERRADO_MAX = 10.0
STALE_DECAY_MONTHS = 12.0
DAYS_PER_MONTH = 30.44
FRESH_SIGNAL_MONTHS = 2  # the panel's month is the last closed one
SIGNAL_AGE_DECAY_MONTHS = 12.0
MIN_SIGNAL_CONFIDENCE = 0.3
PROJECTION_Z_SCALE = 0.05  # 5% a year over the class per unit of z
PROJECTION_FULL_MONTHS = 60
PROJECTION_FRESH_DAYS = 7

_LENS_WORDS = {
    QUALITY: ("qualidade", "acima", "abaixo"),
    VALUATION: ("preço", "mais barato", "mais caro"),
    IMPROVEMENT: ("melhora dos resultados", "acima", "abaixo"),
    MOMENTUM: ("momentum", "acima", "abaixo"),
    INCOME: ("renda", "acima", "abaixo"),
    RISK: ("risco", "menor", "maior"),
}


@dataclass(frozen=True)
class LensScore:
    lens: str
    value: float | None  # L0: 0-10; the others: z (±3); None without data
    normalized: float | None  # [0, 1], higher is better
    confidence: float  # [0, 1]
    note: str
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssetLenses:
    """The lenses of one asset on one date."""

    ticker: str
    as_of: date
    source: str  # PORTFOLIO, WATCHLIST or CATALOG
    arca_class: str | None
    sector: str
    lenses: list[LensScore]
    signal_ticker: str | None = None  # the share class the company's signals are measured on

    def lens(self, key: str) -> LensScore | None:
        return next((s for s in self.lenses if s.lens == key), None)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AssetLenses:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["lenses"] = [LensScore(**s) for s in payload["lenses"]]
        return cls(**payload)


def _decimal(value: float, digits: int = 1, sign: bool = False) -> str:
    text = f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"
    return text.replace(".", ",")


def _pct(value: float, sign: bool = True) -> str:
    return _decimal(value * 100.0, 1, sign) + "%"


# --- L0 Cerrado --------------------------------------------------------------------------------


def _answer_weight(answered_at: datetime | None, validity_months: int, as_of: date) -> float:
    """1 for a current answer; a stale one fades to 0 in 12 months after it expired."""
    if answered_at is None:
        return 1.0
    expiry = answered_at.date() + timedelta(days=round(validity_months * DAYS_PER_MONTH))
    months_past = max((as_of - expiry).days / DAYS_PER_MONTH, 0.0)
    return max(1.0 - months_past / STALE_DECAY_MONTHS, 0.0)


def cerrado_lens(
    evaluation: CerradoEvaluation | None, *, validity_months: int, as_of: date
) -> LensScore:
    """Your analysis on 0-10; not analysed is 0 and keeps competing with a highlight."""
    not_analyzed = LensScore(
        CERRADO,
        0.0,
        0.0,
        1.0,
        "Sem análise do Cerrado: nota 0. Faça a análise: a nota deste ativo pode melhorar e ele "
        "pode ser reclassificado.",
        [NOT_ANALYZED],
    )
    if evaluation is None:
        return not_analyzed
    if not evaluation.use_cerrado:
        return LensScore(
            CERRADO,
            None,
            None,
            0.0,
            "Cerrado desativado para este ativo: a lente sai da nota dele.",
            [CERRADO_OFF],
        )
    net = weight = 0.0
    yes = no = stale = 0
    for answer in evaluation.answers:
        if answer.answer is None:
            continue
        w = (
            _answer_weight(answer.answered_at, validity_months, as_of)
            if answer.stale_reason is not None
            else 1.0
        )
        stale += answer.stale_reason is not None
        yes += answer.answer
        no += not answer.answer
        net += w if answer.answer else -w
        weight += w
    if yes + no == 0:
        return not_analyzed
    applicable = max(evaluation.applicable, 1)
    full = CERRADO_MAX / 2.0 * (net / weight + 1.0) if weight > 0 else 0.0
    coverage = min(weight / applicable, 1.0)
    value = round(full * coverage, 2)
    flags, notes = (
        [],
        [
            f"Nota {_decimal(value)} de 10 ({yes} sim e {no} não em {evaluation.applicable} "
            "perguntas aplicáveis)."
        ],
    )
    if yes + no < evaluation.applicable:
        flags.append(PARTIAL)
        notes.append("Análise incompleta: complete-a, a nota pode subir.")
    if stale:
        flags.append(STALE)
        notes.append(f"{stale} resposta(s) vencida(s): reveja o Cerrado, a nota pode mudar.")
    return LensScore(
        CERRADO, value, round(value / CERRADO_MAX, 4), round(coverage, 4), " ".join(notes), flags
    )


# --- L1 to L6: the point-in-time panel ---------------------------------------------------------


def _months_between(earlier: date, later: date) -> float:
    return (later - earlier).days / DAYS_PER_MONTH


def signal_lens(lens: str, z: float | None, *, month: date | None, as_of: date) -> LensScore:
    """A lens read from the panel: z against the sector, the age of the month in the confidence."""
    word, good, bad = _LENS_WORDS[lens]
    if z is None or month is None:
        return LensScore(
            lens,
            None,
            None,
            0.0,
            f"Sem dado de {word}: o ativo não está no painel de sinais (ações líquidas com "
            "balanço na CVM) ou o balanço é antigo.",
        )
    clipped = max(min(z, WINSOR), -WINSOR)
    age = _months_between(month, as_of)
    confidence = (
        1.0
        if age <= FRESH_SIGNAL_MONTHS
        else max(1.0 - (age - FRESH_SIGNAL_MONTHS) / SIGNAL_AGE_DECAY_MONTHS, MIN_SIGNAL_CONFIDENCE)
    )
    if abs(clipped) < 0.3:
        where = f"{word} na média do setor"
    else:
        side = good if clipped > 0 else bad
        strength = "bem " if abs(clipped) >= 1.0 else ""
        compare = "que o" if lens in (RISK, VALUATION) else "do"
        where = f"{word} {strength}{side} {compare} setor"
    note = f"{where[0].upper()}{where[1:]} (z {_decimal(clipped, sign=True)}, mês {month:%m/%Y})."
    return LensScore(
        lens,
        round(clipped, 4),
        round((clipped + WINSOR) / (2 * WINSOR), 4),
        round(confidence, 4),
        note,
    )


# --- L7 projection -----------------------------------------------------------------------------


def projection_lens(forecast: Mapping[str, Any] | None, *, as_of: date) -> LensScore:
    """Expected return over the class from the forecast's market and event layers (A and C)."""
    if forecast is None:
        return LensScore(PROJECTION, None, None, 0.0, "Sem previsão de preço para este ativo.")
    if forecast.get("status") != "OK":
        return LensScore(
            PROJECTION,
            None,
            None,
            0.0,
            "Previsão de preço sem histórico suficiente para este ativo.",
        )
    drivers = {d["key"]: d.get("annual") for d in forecast.get("drivers", [])}
    expected = float(forecast["expected_total_return_annual"])
    valuation = float(drivers.get("VALUATION") or 0.0)
    market = float(drivers.get("MARKET") or 0.0)
    without_valuation = (1.0 + expected) / (1.0 + valuation) - 1.0
    over_class = (1.0 + without_valuation) / (1.0 + market) - 1.0
    z = max(min(over_class / PROJECTION_Z_SCALE, WINSOR), -WINSOR)
    age_days = (as_of - date.fromisoformat(forecast["as_of"])).days
    confidence = min(forecast.get("months_used", 0) / PROJECTION_FULL_MONTHS, 1.0) * (
        1.0 if age_days <= PROJECTION_FRESH_DAYS else 0.5
    )
    return LensScore(
        PROJECTION,
        round(z, 4),
        round((z + WINSOR) / (2 * WINSOR), 4),
        round(confidence, 4),
        f"A previsão de preço (mercado, desempenho próprio e eventos, sem o valuation) espera "
        f"{_pct(over_class)} ao ano acima da classe (z {_decimal(z, sign=True)}).",
    )


def asset_lenses(
    *,
    ticker: str,
    as_of: date,
    source: str,
    arca_class: str | None,
    sector: str,
    evaluation: CerradoEvaluation | None,
    validity_months: int,
    signals: Mapping[str, float],
    signal_month: date | None,
    forecast: Mapping[str, Any] | None,
    signal_ticker: str | None = None,
) -> AssetLenses:
    """All eight lenses of one asset."""
    lenses: Sequence[LensScore] = [
        cerrado_lens(evaluation, validity_months=validity_months, as_of=as_of),
        *(
            signal_lens(lens, signals.get(signal), month=signal_month, as_of=as_of)
            for lens, signal in LENS_SIGNALS.items()
        ),
        projection_lens(forecast, as_of=as_of),
    ]
    return AssetLenses(
        ticker=ticker,
        as_of=as_of,
        source=source,
        arca_class=arca_class,
        sector=sector,
        lenses=list(lenses),
        signal_ticker=signal_ticker,
    )
