"""Simulation studies (Phase 41): one question, premises set once, chapters that answer it.

A study replaces the loose runs of the six old tabs. Its chapters reuse the Phase 33 engines:

- PAST "De onde viemos": the backtest of the real rules, with the robustness inside;
- FUTURE "Para onde vamos": the projection, with the calibration as its confidence seal;
- IMPROVE "O que pode melhorar": the candidates, on the projection premises of the same study.

Everything here is pure: the facts of each finished chapter come in, the lead sentences, the
"quanto confiar" seals and the conclusion with its next steps come out.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date
from typing import Any


class StudyQuestion:
    COMPLETE = "COMPLETE"  # chapters 1, 2 and 3
    PAST = "PAST"  # "Minhas regras teriam funcionado?"
    GOAL = "GOAL"  # "Vou chegar à minha meta?"
    IMPROVE = "IMPROVE"  # "O que acrescentar à carteira?"


class Chapter:
    PAST = "PAST"
    FUTURE = "FUTURE"
    IMPROVE = "IMPROVE"


CHAPTERS_BY_QUESTION: dict[str, tuple[str, ...]] = {
    StudyQuestion.COMPLETE: (Chapter.PAST, Chapter.FUTURE, Chapter.IMPROVE),
    StudyQuestion.PAST: (Chapter.PAST,),
    StudyQuestion.GOAL: (Chapter.FUTURE,),
    StudyQuestion.IMPROVE: (Chapter.FUTURE, Chapter.IMPROVE),
}

QUESTION_LABELS: dict[str, str] = {
    StudyQuestion.COMPLETE: "Estudo completo",
    StudyQuestion.PAST: "Minhas regras teriam funcionado?",
    StudyQuestion.GOAL: "Vou chegar à minha meta?",
    StudyQuestion.IMPROVE: "O que acrescentar à carteira?",
}

# Chapter -> (number, title, the question its section answers).
CHAPTER_TITLES: dict[str, tuple[int, str, str]] = {
    Chapter.PAST: (1, "De onde viemos", "Se eu tivesse seguido minhas regras, onde estaria?"),
    Chapter.FUTURE: (2, "Para onde vamos", "Vou chegar à minha meta?"),
    Chapter.IMPROVE: (3, "O que pode melhorar", "Que ativo acrescentar aumentaria a minha chance?"),
}

DEFAULT_PAST_START = date(2012, 1, 1)
DEFAULT_BENCHMARKS = ("CDI", "IBOV", "IFIX", "SP500_BRL")
NOMINAL_COVERAGE = 0.90
MIN_CALIBRATION_WINDOWS = 24.0


@dataclass(frozen=True)
class StudyPremises:
    """What every chapter of a study shares; stored as JSON in `simulation_studies.premises`."""

    monthly_contribution: float
    horizon_years: int = 15
    wealth_goal: float | None = None
    correct_by_ipca: bool = True
    past_start: date = DEFAULT_PAST_START
    policy_mode: str = "CURRENT"
    # TODAY: today's checklist answers on every past date (decision P8 of the design).
    answers_mode: str = "TODAY"
    benchmarks: tuple[str, ...] = DEFAULT_BENCHMARKS
    rebalance: bool = False
    include_screener: bool = True
    weight_mode: str = "NEXT_CONTRIBUTION"
    fixed_weight: float = 0.05
    rupture_stress: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["past_start"] = self.past_start.isoformat()
        data["benchmarks"] = list(self.benchmarks)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StudyPremises:
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in data.items() if k in known}
        if isinstance(payload.get("past_start"), str):
            payload["past_start"] = date.fromisoformat(payload["past_start"])
        if "benchmarks" in payload:
            payload["benchmarks"] = tuple(payload["benchmarks"])
        payload.setdefault("monthly_contribution", 0.0)
        return cls(**payload)

    def with_changes(self, changes: dict[str, Any]) -> StudyPremises:
        return StudyPremises.from_dict({**self.to_dict(), **changes})


PREMISE_LABELS: dict[str, str] = {
    "monthly_contribution": "Aporte mensal",
    "horizon_years": "Horizonte (anos)",
    "wealth_goal": "Meta de patrimônio",
    "correct_by_ipca": "Reajuste pelo IPCA",
    "past_start": "Passado desde",
    "policy_mode": "Regras aplicadas",
    "answers_mode": "Checklist no passado",
    "benchmarks": "Referências",
    "rebalance": "Rebalanceamento",
    "include_screener": "Candidatos do screener",
    "weight_mode": "Peso dos candidatos",
    "fixed_weight": "Peso fixo do candidato",
    "rupture_stress": "Ruptura em estresse",
}


def premise_differences(a: StudyPremises, b: StudyPremises) -> list[tuple[str, str, Any, Any]]:
    """(key, label, value in a, value in b) of every premise that differs."""
    left, right = a.to_dict(), b.to_dict()
    return [
        (key, PREMISE_LABELS.get(key, key), left[key], right[key])
        for key in left
        if left[key] != right.get(key)
    ]


# --- formatting (pt-BR) ------------------------------------------------------------------------


def money(value: float) -> str:
    """R$ in short form: R$ 1,31 mi · R$ 412 mil · R$ 980,00."""
    sign = "−" if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000:
        return f"{sign}R$ {v / 1_000_000:.2f} mi".replace(".", ",")
    if v >= 1_000:
        return f"{sign}R$ {v / 1_000:.0f} mil"
    return f"{sign}R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def points(value: float) -> str:
    return f"{value * 100:+.0f} p.p."


# --- seals: "quanto confiar" ---------------------------------------------------------------------

LEVEL_LABELS = {
    4: "Muito confiável",
    3: "Confiável",
    2: "Use com cautela",
    1: "Pouco confiável",
    0: "Sem medição",
}


@dataclass(frozen=True)
class Seal:
    level: int  # 0 (not measured) to 4
    label: str
    text: str


def _level(share: float, limits: tuple[float, float, float]) -> int:
    high, mid, low = limits
    return 4 if share >= high else 3 if share >= mid else 2 if share >= low else 1


def robustness_seal(
    agreeing: int, total: int, worst_crisis: tuple[str, float] | None = None
) -> Seal:
    """How much the past result depends on luck: how many rule variants tell the same story."""
    crisis = (
        f" Na pior crise do período ({worst_crisis[0]}), a carteira caiu "
        f"{pct(abs(worst_crisis[1]))}."
        if worst_crisis is not None and worst_crisis[1] < 0
        else ""
    )
    if total <= 0:
        return Seal(0, LEVEL_LABELS[0], "Este estudo não rodou variantes de regra." + crisis)
    level = _level(agreeing / total, (0.9, 0.7, 0.5))
    text = (
        f"O resultado se manteve em {agreeing} das {total} variantes de regra (outras bandas, "
        f"com e sem rebalanceamento).{crisis}"
    )
    return Seal(level, LEVEL_LABELS[level], text)


def confidence_seal(
    coverage: float | None, windows: float, status: str | None, calibrated_on: date | None
) -> Seal:
    """How much to trust the projection chances: did the 90% band hold in the past?"""
    if coverage is None:
        return Seal(0, LEVEL_LABELS[0], "Ainda não há calibração para medir estas chances.")
    when = f" Calibrado em {calibrated_on.strftime('%d/%m/%Y')}." if calibrated_on else ""
    said = f"Quando o modelo disse 90%, aconteceu em {pct(coverage)} das vezes"
    if windows < MIN_CALIBRATION_WINDOWS or status == "INCONCLUSIVE":
        return Seal(
            1,
            LEVEL_LABELS[1],
            f"{said}, mas em poucas janelas ({windows:.0f}): a amostra é curta.{when}",
        )
    gap = coverage - NOMINAL_COVERAGE
    level = 4 if abs(gap) <= 0.03 else 3 if abs(gap) <= 0.06 else 2 if abs(gap) <= 0.10 else 1
    lean = (
        ", um pouco otimista" if gap < -0.015 else ", um pouco conservador" if gap > 0.015 else ""
    )
    return Seal(level, LEVEL_LABELS[level] + lean, f"{said} em {windows:.0f} janelas.{when}")


# --- chapter facts and leads ---------------------------------------------------------------------


@dataclass(frozen=True)
class PastFacts:
    final_value: float
    contributed: float
    cdi_final: float | None = None
    best_label: str | None = None
    best_final: float | None = None
    annual_irr: float | None = None
    max_drawdown: float = 0.0
    answers_today: bool = False


@dataclass(frozen=True)
class FutureFacts:
    end_year: int
    p50: float
    p5: float
    target: float | None = None
    probability: float | None = None
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class ImproveFacts:
    evaluated: int
    improving: int
    ticker: str | None = None
    base_probability: float | None = None
    new_probability: float | None = None
    p_improve: float | None = None
    delta_wealth: float | None = None


@dataclass(frozen=True)
class Lead:
    tone: str  # positive | negative | caution | neutral
    text: str


def past_lead(f: PastFacts) -> Lead:
    text = f"Seguindo suas regras você teria {money(f.final_value)}"
    tone = "neutral"
    if f.cdi_final is not None:
        gap = f.final_value - f.cdi_final
        side = "acima" if gap >= 0 else "abaixo"
        text += f", {money(abs(gap))} {side} do mesmo fluxo aplicado no CDI"
        tone = "positive" if gap >= 0 else "negative"
    text += "."
    if f.best_label and f.best_final is not None and f.best_final > f.final_value:
        text += f" A melhor referência foi {f.best_label} ({money(f.best_final)})."
    return Lead(tone, text)


def future_lead(f: FutureFacts) -> Lead:
    if f.target is not None and f.probability is not None:
        interval = (
            f" (entre {pct(f.low)} e {pct(f.high)})"
            if f.low is not None and f.high is not None
            else ""
        )
        text = (
            f"A chance de chegar a {money(f.target)} em {f.end_year} é de "
            f"{pct(f.probability)}{interval}. No cenário mediano você chega a {money(f.p50)}; "
            f"nos 5% piores, a {money(f.p5)}."
        )
        tone = (
            "positive"
            if f.probability >= 0.7
            else "caution"
            if f.probability >= 0.4
            else "negative"
        )
        return Lead(tone, text)
    return Lead(
        "neutral",
        f"No cenário mediano o patrimônio chega a {money(f.p50)} em {f.end_year}; nos 5% piores, "
        f"a {money(f.p5)}. Defina uma meta para saber a chance de atingi-la.",
    )


def improve_lead(f: ImproveFacts) -> Lead:
    if f.ticker is None:
        return Lead(
            "neutral",
            f"Nenhum dos {f.evaluated} candidatos melhora a carteira de forma clara: manter o "
            "plano atual é uma resposta válida.",
        )
    if f.base_probability is not None and f.new_probability is not None:
        effect = (
            f"eleva a chance da meta de {pct(f.base_probability)} para {pct(f.new_probability)}"
        )
    else:
        effect = f"muda o patrimônio mediano em {money(f.delta_wealth or 0.0)}"
    real = f"; a melhora é real com {pct(f.p_improve)} de probabilidade" if f.p_improve else ""
    return Lead(
        "positive",
        f"Incluir {f.ticker} no próximo aporte {effect}{real}. Dos {f.evaluated} candidatos, "
        f"{f.improving} melhoram a carteira.",
    )


# --- conclusion ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    kind: str  # VARIATION | COMPARE_ASSET | CONTRIBUTE | SET_GOAL
    label: str
    ticker: str | None = None
    changes: dict[str, Any] = field(default_factory=dict)


def suggested_contribution(monthly: float) -> float:
    """A round 20% more, the variation the conclusion offers to simulate."""
    return float(max(100, round(monthly * 1.2 / 100) * 100))


def conclusion(
    premises: StudyPremises,
    past: PastFacts | None,
    past_seal: Seal | None,
    future: FutureFacts | None,
    future_seal: Seal | None,
    improve: ImproveFacts | None,
) -> tuple[str, list[Action]]:
    """The study in 3 to 5 sentences, built only from the chapters, and its next steps."""
    sentences: list[str] = []
    actions: list[Action] = []
    if past is not None:
        if past.cdi_final is not None:
            gap = past.final_value - past.cdi_final
            verdict = "teriam funcionado" if gap >= 0 else "teriam ficado atrás do CDI"
            sentence = (
                f"Suas regras {verdict}: {money(abs(gap))} "
                f"{'acima' if gap >= 0 else 'abaixo'} do CDI desde "
                f"{premises.past_start.year}"
            )
        else:
            sentence = f"Suas regras teriam levado a {money(past.final_value)}"
        if past_seal is not None and past_seal.level >= 3:
            sentence += ", e o resultado não dependeu de um período sortudo"
        elif past_seal is not None and 0 < past_seal.level <= 2:
            sentence += ", mas o resultado muda bastante com outras regras"
        sentences.append(sentence + ".")
    if future is not None:
        if future.probability is not None and future.target is not None:
            trust = (
                f", com chances {future_seal.label.lower()}"
                if future_seal is not None and future_seal.level > 0
                else ""
            )
            sentences.append(
                f"Daqui para frente, a chance de chegar a {money(future.target)} é de "
                f"{pct(future.probability)}{trust}."
            )
        else:
            sentences.append(
                f"Daqui para frente, o patrimônio mediano chega a {money(future.p50)} em "
                f"{future.end_year}."
            )
            actions.append(Action("SET_GOAL", "Definir uma meta de patrimônio"))
    if improve is not None and improve.ticker is not None:
        gain = (
            f" ({points(improve.new_probability - improve.base_probability)})"
            if improve.new_probability is not None and improve.base_probability is not None
            else ""
        )
        sentences.append(f"O candidato mais promissor é {improve.ticker}{gain}.")
        actions.append(
            Action(
                "COMPARE_ASSET", f"Estudar {improve.ticker} no comparador", ticker=improve.ticker
            )
        )
    if future is not None and premises.monthly_contribution > 0:
        more = suggested_contribution(premises.monthly_contribution)
        label = f"Simular aporte de {money(more)}".replace(" mil", " mil/mês")
        actions.insert(0, Action("VARIATION", label, changes={"monthly_contribution": more}))
    actions.append(Action("CONTRIBUTE", "Ir para Aportar"))
    return " ".join(sentences), actions


def with_label(premises: StudyPremises, changes: dict[str, Any]) -> str:
    """The name suffix of a variation: what changed, in words."""
    parts = []
    for key, value in changes.items():
        if key == "monthly_contribution":
            parts.append(f"aporte {money(float(value))}")
        elif key == "horizon_years":
            parts.append(f"{value} anos")
        elif key == "wealth_goal" and value:
            parts.append(f"meta {money(float(value))}")
        else:
            parts.append(PREMISE_LABELS.get(key, key).lower())
    return ", ".join(parts) or "variação"


def replace_premises(premises: StudyPremises, **changes: Any) -> StudyPremises:
    return replace(premises, **changes)
