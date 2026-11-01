"""Repository port of the live scoreboard (Phase 45.8a)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from domain.comparison.points import Point


@dataclass
class ComparisonPortfolio:
    """One comparison portfolio: its rule, the day it was created and its record.

    The points before `created_on` were rebuilt from the past (retroactive, labelled); from that
    day on they are the prospective record, only ever appended to (decision 10.1.9). `state`
    keeps the book, so the daily routine resumes where it stopped.
    """

    key: str
    variant: int
    label: str
    created_on: date
    state: dict[str, Any] = field(default_factory=dict)
    points: list[Point] = field(default_factory=list)
    id: int | None = None


class AbstractComparisonRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[ComparisonPortfolio]: ...

    @abstractmethod
    def get(self, key: str, variant: int = 0) -> ComparisonPortfolio | None: ...

    @abstractmethod
    def save(self, portfolio: ComparisonPortfolio) -> None: ...
