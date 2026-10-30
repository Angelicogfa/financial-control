"""The gates of the recommendation (Phase 45.2, design N3): who cannot receive money, and why.

A gate only eliminates for what is objective and serious; everything else is a weight in the
lenses (the Cerrado is never a gate, decision 10.2). Each gate gives PASS, FAIL, WARN (shown,
does not eliminate) or NOT_APPLICABLE, always with the reason.

- LEDGER: the asset's own entries must make sense (no sale without the units).
- LIQUIDITY: the average daily volume must reach the floor of its class.
- HISTORY: at least 12 months of stored prices, or the risk and projection cannot be measured.
- RUIN: no Altman Z'' in the distress zone and no judicial recovery in the last two years.
- DATA: indicators the providers' sanity check flagged as suspicious. A warning only: the lenses
  read the statements delivered to the CVM, not those indicators; the Cerrado's automatic
  answers and the classic valuation do read them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
NOT_APPLICABLE = "NOT_APPLICABLE"

LEDGER = "LEDGER"
LIQUIDITY = "LIQUIDITY"
HISTORY = "HISTORY"
RUIN = "RUIN"
DATA = "DATA"
GATES = (LEDGER, LIQUIDITY, HISTORY, RUIN, DATA)

GATE_LABELS = {
    LEDGER: "Lançamentos",
    LIQUIDITY: "Liquidez",
    HISTORY: "Histórico de preço",
    RUIN: "Risco de ruína",
    DATA: "Dados do provedor",
}

MIN_HISTORY_MONTHS = 12
ALTMAN_DISTRESS = 1.1
RESTRUCTURING_LOOKBACK_DAYS = 730
DAYS_PER_MONTH = 30.44


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str
    reason: str


@dataclass(frozen=True)
class AssetGates:
    ticker: str
    results: list[GateResult] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return all(r.status != FAIL for r in self.results)

    def failed(self) -> list[GateResult]:
        return [r for r in self.results if r.status == FAIL]


def _decimal(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"R$ {value / 1_000_000:.1f} mi".replace(".", ",")
    return f"R$ {value / 1_000:.0f} mil"


def ledger_gate(valid: bool | None) -> GateResult:
    """`valid` None: not registered (a catalog asset has no entries)."""
    if valid is None:
        return GateResult(LEDGER, NOT_APPLICABLE, "Ativo do catálogo, sem lançamentos.")
    if valid:
        return GateResult(LEDGER, PASS, "Lançamentos consistentes.")
    return GateResult(
        LEDGER,
        FAIL,
        "Lançamentos inconsistentes (venda maior que a posição): corrija o extrato do ativo.",
    )


def liquidity_gate(volume: float | None, floor: float | None) -> GateResult:
    """`floor` None: the class has no floor (international assets, for instance)."""
    if floor is None:
        return GateResult(LIQUIDITY, NOT_APPLICABLE, "Sem piso de liquidez para esta classe.")
    if volume is None:
        return GateResult(LIQUIDITY, FAIL, "Sem volume negociado guardado para medir a liquidez.")
    if volume < floor:
        return GateResult(
            LIQUIDITY,
            FAIL,
            f"Volume médio de {_money(volume)} por dia, abaixo do piso de {_money(floor)}.",
        )
    return GateResult(LIQUIDITY, PASS, f"Volume médio de {_money(volume)} por dia.")


def history_gate(first: date | None, as_of: date) -> GateResult:
    if first is None:
        return GateResult(HISTORY, FAIL, "Sem histórico de preço guardado.")
    months = (as_of - first).days / DAYS_PER_MONTH
    if months < MIN_HISTORY_MONTHS:
        return GateResult(
            HISTORY,
            FAIL,
            f"Só {months:.0f} meses de histórico de preço; são precisos {MIN_HISTORY_MONTHS} "
            "para medir risco e projeção.",
        )
    return GateResult(HISTORY, PASS, f"{months:.0f} meses de histórico de preço.")


def ruin_gate(
    altman: float | None, restructuring: Sequence[date], *, applies_altman: bool, as_of: date
) -> GateResult:
    recent = [d for d in restructuring if 0 <= (as_of - d).days <= RESTRUCTURING_LOOKBACK_DAYS]
    if recent:
        return GateResult(
            RUIN,
            FAIL,
            f"Comunicado de recuperação judicial ou reestruturação de dívida em "
            f"{max(recent):%d/%m/%Y}.",
        )
    if applies_altman and altman is not None and altman < ALTMAN_DISTRESS:
        return GateResult(
            RUIN,
            FAIL,
            f"Altman Z'' de {_decimal(altman)}, na zona de estresse (abaixo de "
            f"{_decimal(ALTMAN_DISTRESS, 1)}).",
        )
    if not applies_altman:
        return GateResult(RUIN, PASS, "Sem recuperação judicial recente (Altman não se aplica).")
    if altman is None:
        return GateResult(RUIN, PASS, "Sem recuperação judicial recente; Altman sem dados.")
    return GateResult(
        RUIN, PASS, f"Sem recuperação judicial recente; Altman Z'' de {_decimal(altman)}."
    )


def data_gate(suspicious: Mapping[str, str] | None) -> GateResult:
    if suspicious is None:
        return GateResult(DATA, NOT_APPLICABLE, "Sem indicadores do provedor guardados.")
    if suspicious:
        fields = ", ".join(sorted(suspicious))
        return GateResult(
            DATA,
            WARN,
            f"Indicadores suspeitos no provedor ({fields}): as lentes usam os balanços da CVM, "
            "mas as respostas automáticas do Cerrado e o valuation clássico os leem.",
        )
    return GateResult(DATA, PASS, "Indicadores do provedor dentro das faixas plausíveis.")


def asset_gates(
    *,
    ticker: str,
    as_of: date,
    ledger_valid: bool | None,
    volume: float | None,
    liquidity_floor: float | None,
    first_price: date | None,
    altman: float | None,
    applies_altman: bool,
    restructuring: Sequence[date],
    suspicious: Mapping[str, str] | None,
) -> AssetGates:
    return AssetGates(
        ticker,
        [
            ledger_gate(ledger_valid),
            liquidity_gate(volume, liquidity_floor),
            history_gate(first_price, as_of),
            ruin_gate(altman, restructuring, applies_altman=applies_altman, as_of=as_of),
            data_gate(suspicious),
        ],
    )
