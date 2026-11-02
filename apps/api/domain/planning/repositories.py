"""Repository port of the goals (Phase 48.R8)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.planning.goals import Goal


class AbstractGoalRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Goal]: ...

    @abstractmethod
    def get(self, goal_id: int) -> Goal | None: ...

    @abstractmethod
    def add(self, goal: Goal) -> Goal: ...

    @abstractmethod
    def update(self, goal: Goal) -> Goal: ...

    @abstractmethod
    def delete(self, goal_id: int) -> bool: ...
