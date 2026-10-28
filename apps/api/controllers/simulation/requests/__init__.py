"""Pydantic request DTOs for the simulation module (Phase 33)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

BenchmarkKey = Literal["CDI", "IBOV", "IFIX", "SP500_BRL"]


class BacktestRequest(BaseModel):
    """A strategy backtest: the real contribution rules replayed over the stored history."""

    start: date
    end: date
    monthly_contribution: float = Field(gt=0, le=10_000_000)
    initial_contribution: float = Field(default=0.0, ge=0, le=100_000_000)
    correct_by_ipca: bool = False
    fee_rate: float = Field(default=0.0003, ge=0, le=0.05)
    rebalance: bool = False
    universe: Literal["REGISTERED", "REGISTERED_AND_CATALOG"] = "REGISTERED"
    # Catalog instruments added with REGISTERED_AND_CATALOG (default: the server setting).
    catalog_top: int | None = Field(default=None, ge=0, le=500)
    policy_mode: Literal["CURRENT", "AS_OF"] = "CURRENT"
    benchmarks: list[BenchmarkKey] = Field(default_factory=lambda: ["CDI", "IBOV"])
    # Also run the rule variants (bands x rebalancing) shown in the Robustness view.
    variants: bool = False
    label: str | None = Field(default=None, max_length=120)
