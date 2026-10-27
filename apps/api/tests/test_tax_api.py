"""Integration tests of the tax module: migration seed, REST routes and MCP operations."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from controllers.tax.requests import FixedIncomeCompareRequest
from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.portfolio.services.service import PortfolioApplicationService
from domain.tax.entities import TaxBracket, TaxKind, TaxRegime, TaxRule
from domain.tax.services.rules import DEFAULT_TAX_RULES
from tests.conftest import offline_gateway

API_DIR = Path(__file__).resolve().parents[1]


def _create_cdb(api: SimpleNamespace, *, start: date, amount: str = "10000") -> int:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": "CDB-TAX",
            "name": "CDB 110% CDI",
            "asset_type": "FIXED_INCOME",
            "fixed_income_term": {
                "instrument_kind": "CDB",
                "indexer": "CDI",
                "contracted_rate": "1.10",
                "issue_date": start.isoformat(),
                "maturity_date": (start + timedelta(days=1000)).isoformat(),
            },
        },
    )
    assert resp.status_code == 201, resp.text
    asset_id = resp.json()["id"]
    trade = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": start.isoformat(),
            "quantity": "1",
            "unit_price": amount,
        },
    )
    assert trade.status_code == 201, trade.text
    return asset_id


def test_script_00019_creates_and_seeds_tax_rules(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'tax_mig.db').as_posix()}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    try:
        command.upgrade(cfg, "script_00018")
        assert "tax_rules" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "script_00019")
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM tax_rules")).scalar_one()
        assert count == len(DEFAULT_TAX_RULES)
        command.downgrade(cfg, "script_00018")
        assert "tax_rules" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_seeded_rules_match_the_built_in_registry(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        stored = uow.tax_rules.list_all()
    key = lambda r: (r.regime, r.valid_from)  # noqa: E731
    assert [
        (r.regime, r.tax_kind, r.brackets, r.valid_from, r.valid_to, r.legal_basis, r.description)
        for r in sorted(stored, key=key)
    ] == [
        (r.regime, r.tax_kind, r.brackets, r.valid_from, r.valid_to, r.legal_basis, r.description)
        for r in sorted(DEFAULT_TAX_RULES, key=key)
    ]


def test_list_rules_route(api: SimpleNamespace) -> None:
    resp = api.client.get("/api/v1/tax/rules")
    assert resp.status_code == 200
    rules = resp.json()
    jcp = [r for r in rules if r["regime"] == "JCP_WITHHOLDING"]
    assert [r["brackets"][0]["rate"] for r in jcp] == [0.15, 0.175]
    assert jcp[0]["valid_to"] == "2025-12-31"
    assert all(r["id"] is not None for r in rules)


def test_new_rule_record_changes_the_valuation_from_its_start(api: SimpleNamespace) -> None:
    start = date(2026, 1, 2)
    asset_id = _create_cdb(api, start=start)
    after = (start + timedelta(days=200)).isoformat()
    before_change = (start + timedelta(days=150)).isoformat()
    assert _lot_rate(api, asset_id, after) == 0.2

    # A legal change: close the current record and insert the new one (as a migration does).
    with api.uow_factory() as uow:
        uow.session.execute(
            text(
                "UPDATE tax_rules SET valid_to = '2026-06-30' "
                "WHERE regime = 'FIXED_INCOME_REGRESSIVE'"
            )
        )
        uow.tax_rules.add(
            TaxRule(
                TaxRegime.FIXED_INCOME_REGRESSIVE,
                TaxKind.INCOME_TAX,
                (TaxBracket(None, 0.10),),
                date(2026, 7, 1),
                legal_basis="Lei hipotética",
            )
        )
        uow.commit()

    assert _lot_rate(api, asset_id, after) == 0.1
    assert _lot_rate(api, asset_id, before_change) == 0.225
    report = api.client.get(f"/api/v1/portfolio?as_of_date={after}").json()
    position = next(p for p in report["positions"] if p["asset_id"] == asset_id)
    assert position["fixed_income_details"]["income_tax_rate"] == 0.1


def _lot_rate(api: SimpleNamespace, asset_id: int, as_of: str) -> float:
    resp = api.client.get(f"/api/v1/tax/assets/{asset_id}/status?as_of_date={as_of}")
    assert resp.status_code == 200, resp.text
    return resp.json()["lots"][0]["income_tax_rate"]


def test_asset_tax_status_route(api: SimpleNamespace) -> None:
    start = date(2026, 1, 2)
    asset_id = _create_cdb(api, start=start)
    as_of = (start + timedelta(days=180)).isoformat()

    resp = api.client.get(f"/api/v1/tax/assets/{asset_id}/status?as_of_date={as_of}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_fixed_income"] is True
    lot = body["lots"][0]
    assert lot["income_tax_rate"] == 0.225
    assert lot["next_bracket_date"] == (start + timedelta(days=181)).isoformat()
    assert lot["days_to_next_bracket"] == 1
    assert lot["tax_saving_by_waiting"] > 0
    assert body["regimes"][0]["regime"] == "FIXED_INCOME_REGRESSIVE"

    report = api.client.get(f"/api/v1/portfolio?as_of_date={as_of}").json()
    position = next(p for p in report["positions"] if p["asset_id"] == asset_id)
    assert position["fixed_income_details"]["income_tax"] == lot["income_tax_due"]


def test_asset_tax_status_for_market_asset_and_missing_asset(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/assets", json={"ticker": "ITUB4", "name": "Itaú", "asset_type": "STOCK_BR"}
    )
    asset_id = created.json()["id"]
    body = api.client.get(f"/api/v1/tax/assets/{asset_id}/status").json()
    assert body["is_fixed_income"] is False
    assert body["lots"] == []
    regimes = {r["regime"]: r["current_rate"] for r in body["regimes"]}
    assert regimes["STOCK_SWING_TRADE"] == 0.15

    missing = api.client.get("/api/v1/tax/assets/99999/status")
    assert missing.status_code == 404


def test_compare_route_with_manual_and_portfolio_offers(api: SimpleNamespace) -> None:
    start = date(2026, 1, 2)
    asset_id = _create_cdb(api, start=start)
    resp = api.client.post(
        "/api/v1/tax/fixed-income/compare",
        json={
            "start_date": start.isoformat(),
            "principal": 5000,
            "offers": [
                {"asset_id": asset_id},
                {
                    "label": "LCA 90%",
                    "indexer": "CDI_PERCENT",
                    "rate": 0.9,
                    "term_days": 720,
                    "tax_exempt": True,
                },
            ],
            "scenarios": [{"name": "BASE", "annual_cdi_rate": 0.14, "annual_ipca_rate": 0.045}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    portfolio_offer = body["offers"][0]
    assert portfolio_offer == {
        "label": "CDB-TAX",
        "asset_id": asset_id,
        "indexer": "CDI_PERCENT",
        "rate": 1.1,
        "term_days": 1000,
        "tax_exempt": False,
        "grace_days": 1000,
    }
    assert body["common_window_days"] == 720
    assert body["principal"] == 5000
    assert len(body["projections"]) == 2
    cdb = next(p for p in body["projections"] if p["label"] == "CDB-TAX")
    assert cdb["at_common_window"]["redeemable"] is False
    assert body["best_by_scenario"] == {"BASE": "LCA 90%"}


def test_compare_route_uses_policy_scenarios_and_validates(api: SimpleNamespace) -> None:
    offers = [
        {"indexer": "PRE", "rate": 0.13, "term_days": 400},
        {"indexer": "IPCA_SPREAD", "rate": 0.07, "term_days": 800, "tax_exempt": True},
    ]
    resp = api.client.post("/api/v1/tax/fixed-income/compare", json={"offers": offers})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["name"] for s in body["scenarios"]] == ["LOW", "BASE", "HIGH"]
    assert [o["label"] for o in body["offers"]] == ["Título 1", "Título 2"]

    incomplete = api.client.post(
        "/api/v1/tax/fixed-income/compare",
        json={"offers": [{"indexer": "PRE", "rate": 0.1}, offers[0]]},
    )
    assert incomplete.status_code == 400
    assert incomplete.json()["code"] == "INCOMPLETE_OFFER"

    stock = api.client.post(
        "/api/v1/assets", json={"ticker": "PETR4", "name": "Petro", "asset_type": "STOCK_BR"}
    ).json()
    not_fixed = api.client.post(
        "/api/v1/tax/fixed-income/compare",
        json={"offers": [{"asset_id": stock["id"]}, offers[0]]},
    )
    assert not_fixed.status_code == 400
    assert not_fixed.json()["code"] == "ASSET_WITHOUT_FIXED_INCOME_TERM"

    too_few = api.client.post("/api/v1/tax/fixed-income/compare", json={"offers": offers[:1]})
    assert too_few.status_code == 422


def test_mcp_operations_are_in_the_catalog_and_run(api: SimpleNamespace) -> None:
    for name in ("assets.tax_status", "tools.fixed_income_compare", "tools.tax_rules"):
        assert CATALOG_BY_NAME[name].kind == "query"
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    start = date(2026, 1, 2)
    asset_id = _create_cdb(api, start=start)

    status_op = CATALOG_BY_NAME["assets.tax_status"]
    status = status_op.invoke(
        handlers,
        status_op.input_model(asset_id=asset_id, as_of_date=start + timedelta(days=10)),
    )
    assert status.lots[0].iof_due > 0

    compare_op = CATALOG_BY_NAME["tools.fixed_income_compare"]
    comparison = compare_op.invoke(
        handlers,
        FixedIncomeCompareRequest.model_validate(
            {
                "offers": [
                    {"asset_id": asset_id},
                    {"indexer": "PRE", "rate": 0.12, "term_days": 365},
                ]
            }
        ),
    )
    assert comparison.offers[0].asset_id == asset_id

    rules = CATALOG_BY_NAME["tools.tax_rules"].invoke(handlers, None)
    assert {r.regime for r in rules} >= {TaxRegime.JCP_WITHHOLDING, TaxRegime.IOF_REGRESSIVE}
