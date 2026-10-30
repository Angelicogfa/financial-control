"""Phase 45.2: the gates of the recommendation, only for what is objective and serious."""

from __future__ import annotations

from datetime import date

from domain.recommendation.gates import (
    DATA,
    FAIL,
    LEDGER,
    LIQUIDITY,
    NOT_APPLICABLE,
    PASS,
    RUIN,
    WARN,
    asset_gates,
    data_gate,
    history_gate,
    ledger_gate,
    liquidity_gate,
    ruin_gate,
)

TODAY = date(2026, 10, 31)


def test_ledger_gate() -> None:
    assert ledger_gate(True).status == PASS
    failed = ledger_gate(False)
    assert failed.status == FAIL and "corrija o extrato" in failed.reason
    assert ledger_gate(None).status == NOT_APPLICABLE


def test_liquidity_gate() -> None:
    assert liquidity_gate(5_000_000, 1_000_000).reason == "Volume médio de R$ 5,0 mi por dia."
    low = liquidity_gate(300_000, 1_000_000)
    assert low.status == FAIL and "R$ 300 mil" in low.reason and "R$ 1,0 mi" in low.reason
    assert liquidity_gate(None, 1_000_000).status == FAIL
    assert liquidity_gate(None, None).status == NOT_APPLICABLE


def test_history_gate() -> None:
    assert history_gate(date(2020, 1, 2), TODAY).status == PASS
    short = history_gate(date(2026, 3, 1), TODAY)
    assert short.status == FAIL and "são precisos 12" in short.reason
    assert history_gate(None, TODAY).status == FAIL


def test_ruin_gate() -> None:
    recovery = ruin_gate(3.0, [date(2025, 6, 10)], applies_altman=True, as_of=TODAY)
    assert recovery.status == FAIL and "10/06/2025" in recovery.reason
    old = ruin_gate(3.0, [date(2023, 1, 10)], applies_altman=True, as_of=TODAY)
    assert old.status == PASS  # more than two years ago
    distress = ruin_gate(0.8, [], applies_altman=True, as_of=TODAY)
    assert distress.status == FAIL and "0,80" in distress.reason and "1,1" in distress.reason
    assert ruin_gate(0.8, [], applies_altman=False, as_of=TODAY).status == PASS  # a bank
    assert ruin_gate(None, [], applies_altman=True, as_of=TODAY).status == PASS


def test_suspicious_data_only_warns() -> None:
    warned = data_gate({"net_margin": "margem acima de 100%"})
    assert warned.status == WARN and "net_margin" in warned.reason
    assert data_gate({}).status == PASS
    assert data_gate(None).status == NOT_APPLICABLE


def test_one_fail_takes_the_asset_out_a_warning_does_not() -> None:
    args = {
        "ticker": "AAAA3",
        "as_of": TODAY,
        "ledger_valid": True,
        "volume": 2_000_000.0,
        "liquidity_floor": 1_000_000.0,
        "first_price": date(2019, 1, 2),
        "altman": 3.0,
        "applies_altman": True,
        "restructuring": [],
        "suspicious": {"roe": "fora da faixa"},
    }
    fine = asset_gates(**args)
    assert fine.eligible and [r.gate for r in fine.results][0] == LEDGER
    assert {r.gate: r.status for r in fine.results}[DATA] == WARN
    illiquid = asset_gates(**{**args, "volume": 10_000.0})
    assert not illiquid.eligible and [r.gate for r in illiquid.failed()] == [LIQUIDITY]
    ruined = asset_gates(**{**args, "restructuring": [date(2026, 9, 1)]})
    assert [r.gate for r in ruined.failed()] == [RUIN]
