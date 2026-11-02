"""Repository ports of the alert rules and the asset notes (Phase 48.R6)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.watch.entities import AlertRule, AssetNote


class AbstractAlertRuleRepository(ABC):
    @abstractmethod
    def list_all(self, *, active_only: bool = False) -> list[AlertRule]: ...

    @abstractmethod
    def get(self, rule_id: int) -> AlertRule | None: ...

    @abstractmethod
    def add(self, rule: AlertRule) -> AlertRule: ...

    @abstractmethod
    def update(self, rule: AlertRule) -> AlertRule: ...

    @abstractmethod
    def delete(self, rule_id: int) -> bool: ...


class AbstractAssetNoteRepository(ABC):
    @abstractmethod
    def list_for_asset(self, asset_id: int) -> list[AssetNote]:
        """Newest first."""

    @abstractmethod
    def list_all(self) -> list[AssetNote]: ...

    @abstractmethod
    def get(self, note_id: int) -> AssetNote | None: ...

    @abstractmethod
    def add(self, note: AssetNote) -> AssetNote: ...

    @abstractmethod
    def update(self, note: AssetNote) -> AssetNote: ...

    @abstractmethod
    def delete(self, note_id: int) -> bool: ...
