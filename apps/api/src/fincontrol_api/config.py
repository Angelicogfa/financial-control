"""API configuration: re-exports the shared settings."""

from __future__ import annotations

from fincontrol_config import Settings, get_settings

AppSettings = Settings

__all__ = ["AppSettings", "Settings", "get_settings"]
