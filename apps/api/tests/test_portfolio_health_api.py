"""Integration tests of the portfolio health diagnosis (Phase 29): route, policy, MCP, migration."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import PortfolioSnapshotEntity
from tests.conftest import offline_gateway

API_DIR = Path(__file__).resolve().parents[1]
START = date(2026, 1, 2)
AS_OF = date(2026, 10, 27)


def _create_cdb(api: SimpleNamespace, ticker: str, issuer: str | None, amount: str) -> int:
    term: dict[str, object] = {
        "instrument_kind": "CDB",
        "indexer": "CDI",
        "contracted_rate": "1.10",
        "maturity_date": (AS_OF + timedelta(days=120)).isoformat(),
    }
    if issuer:
        term["issuer"] = issuer
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": ticker,
            "name": f"CDB {ticker}",
            "asset_type": "FIXED_INCOME",
            "fixed_income_term": term,
        },
    )
    assert resp.status_code == 201, resp.text
    asset_id = resp.json()["id"]
    trade = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": START.isoformat(),
            "quantity": "1",
            "unit_price": amount,
        },
    )
    assert trade.status_code == 201, trade.text
    return asset_id


def _pillar(body: dict, key: str) -> dict:
    return next(p for p in body["pillars"] if p["pillar"] == key)


def _check(body: dict, key: str) -> dict:
    return next(c for p in body["pillars"] for c in p["checks"] if c["key"] == key)


def test_health_route_returns_seven_pillars_worst_first(api: SimpleNamespace) -> None:
    _create_cdb(api, "CDB-A", "Banco A", "300000")
    _create_cdb(api, "CDB-B", None, "20000")

    resp = api.client.get(f"/api/v1/portfolio/health?as_of_date={AS_OF.isoformat()}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["pillars"]) == 7
    assert body["status"] == "CRITICAL"
    assert body["pillars"][0]["status"] == "CRITICAL"
    fgc = _check(body, "fgc_exposure")
    assert fgc["status"] == "CRITICAL"
    assert body["institutions"][0]["issuer"] == "BANCO A"
    assert body["institutions"][0]["usage"] > 1.0
    assert _check(body, "maturities_12m")["value"] > 0
    assert _check(body, "volatility")["status"] == "INSUFFICIENT_DATA"
    assert _check(body, "emergency_reserve")["status"] == "INSUFFICIENT_DATA"
    assert _pillar(body, "PERFORMANCE")["status"] == "INSUFFICIENT_DATA"


def test_health_uses_snapshots_and_policy_limits(api: SimpleNamespace) -> None:
    _create_cdb(api, "CDB-A", "Banco A", "10000")
    with api.uow_factory() as uow:
        value = 10_000.0
        for i in range(80):
            value *= 1.0 + (0.002 if i % 2 else -0.001)
            uow.snapshots.upsert(
                PortfolioSnapshotEntity(
                    snapshot_date=AS_OF - timedelta(days=80 - i),
                    invested_value=10_000.0,
                    market_value=value,
                    unrealized_pnl=value - 10_000.0,
                )
            )
        uow.commit()

    policy = api.client.get("/api/v1/policy").json()
    policy["health"]["monthly_expenses_brl"] = 1000.0
    policy["health"]["min_observations"] = 30
    saved = api.client.put("/api/v1/policy", json=policy)
    assert saved.status_code == 200, saved.text
    assert saved.json()["health"]["monthly_expenses_brl"] == 1000.0

    body = api.client.get(f"/api/v1/portfolio/health?as_of_date={AS_OF.isoformat()}").json()

    volatility = _check(body, "volatility")
    assert volatility["status"] != "INSUFFICIENT_DATA"
    assert volatility["observations"] == 79
    assert body["risk"]["volatility"] is not None
    assert _check(body, "emergency_reserve")["value"] == 0.0
    assert _check(body, "emergency_reserve")["status"] == "CRITICAL"


def test_policy_keeps_health_defaults_and_rejects_bad_limits(api: SimpleNamespace) -> None:
    policy = api.client.get("/api/v1/policy").json()
    assert policy["health"]["fgc_limit_brl"] == 250_000.0
    assert policy["health"]["monthly_expenses_brl"] is None

    policy["health"]["max_asset_weight_warning"] = 0.5
    policy["health"]["max_asset_weight_critical"] = 0.2
    resp = api.client.put("/api/v1/policy", json=policy)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_HEALTH_LIMIT"

    legacy = {k: v for k, v in policy.items() if k not in ("health", "version", "created_at")}
    assert api.client.put("/api/v1/policy", json=legacy).status_code == 200


def test_mcp_portfolio_health_operation(api: SimpleNamespace) -> None:
    _create_cdb(api, "CDB-A", "Banco A", "10000")
    op = CATALOG_BY_NAME["portfolio.health"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )

    result = op.invoke(handlers, op.input_model(as_of_date=AS_OF))

    assert op.kind == "query"
    assert len(result.pillars) == 7
    assert result.total_value_brl > 10_000


def test_script_00021_adds_health_limits_column(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'health_mig.db').as_posix()}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    try:
        command.upgrade(cfg, "script_00021")
        columns = {c["name"] for c in inspect(engine).get_columns("investment_policies")}
        assert "health" in columns
        command.downgrade(cfg, "script_00020")
        columns = {c["name"] for c in inspect(engine).get_columns("investment_policies")}
        assert "health" not in columns
    finally:
        engine.dispose()
