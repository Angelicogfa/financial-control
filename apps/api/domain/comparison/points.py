"""One recorded value of a comparison portfolio, free of imports (the repository port uses it)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Point:
    day: date
    flow: float
    contributed: float
    value: float
    cash: float
    fees: float
    taxes: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "flow": self.flow,
            "contributed": self.contributed,
            "value": self.value,
            "cash": self.cash,
            "fees": self.fees,
            "taxes": self.taxes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Point:
        return cls(
            day=date.fromisoformat(data["day"]),
            flow=float(data["flow"]),
            contributed=float(data["contributed"]),
            value=float(data["value"]),
            cash=float(data["cash"]),
            fees=float(data["fees"]),
            taxes=float(data["taxes"]),
        )
