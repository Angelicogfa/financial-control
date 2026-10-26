"""Unit tests keeping Settings and .env.example in lockstep (finding I-08)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fincontrol_config import COMPOSE_ONLY_VARIABLES, Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[4] / ".env.example"


def _example_variables() -> dict[str, str]:
    variables: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        variables[name.strip()] = value.strip()
    return variables


def test_every_example_variable_is_consumed() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    unused = set(_example_variables()) - fields - COMPOSE_ONLY_VARIABLES
    assert not unused, f".env.example variables nobody reads: {sorted(unused)}"


def test_every_setting_is_documented_in_example() -> None:
    undocumented = {name.upper() for name in Settings.model_fields} - set(_example_variables())
    assert not undocumented, f"Settings missing from .env.example: {sorted(undocumented)}"


def test_example_values_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _example_variables().items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert settings.quote_cache_ttl == 300
    assert settings.cors_origin_list == ["http://localhost:5173", "http://localhost:8080"]
    assert settings.redis_url == "redis://:change-me-redis@redis:6379/0"


def test_auth_is_configured_only_with_hash_and_secret() -> None:
    assert not Settings(_env_file=None).auth_configured
    assert not Settings(
        _env_file=None, auth_password_hash="change-me", auth_jwt_secret="change-me"
    ).auth_configured
    assert Settings(
        _env_file=None, auth_password_hash="$argon2id$x", auth_jwt_secret="s" * 32
    ).auth_configured


def test_auth_is_not_configured_when_the_hash_is_not_argon2() -> None:
    # A plain password, or a hash whose "$" parts were expanded away by the shell/compose.
    for value in ("my-plain-password", "=19=65536,t=3,p=4"):
        assert not Settings(
            _env_file=None, auth_password_hash=value, auth_jwt_secret="s" * 32
        ).auth_configured
