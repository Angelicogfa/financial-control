"""Database readiness reported by the probe the composition root injects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseStatus:
    reachable: bool
    current_revision: str | None
    head_revision: str | None
    error: str | None = None

    @property
    def migrated(self) -> bool:
        return self.reachable and self.current_revision == self.head_revision
