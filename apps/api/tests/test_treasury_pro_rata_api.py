"""Integration tests of pro-rata Treasury accrual: optional issue date and LTN purchase rates."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from core.helpers.calendar import business_days_between
from domain.shared.enums import SeriesUnit

API_DIR = Path(__file__).resolve().parents[1]
PURCHASE = date(2026, 3, 17)
MATURITY = date(2029, 1, 1)
AS_OF = date(2026, 10, 27)


def _ltn_price(rate: float) -> float:
    business_days = len(business_days_between(PURCHASE, MATURITY))
    return round(1000.0 / (1.0 + rate) ** (business_days / 252.0), 6)


def _create_prefixado(api: SimpleNamespace, name: str, **term: object) -> int:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "name": name,
            "asset_type": "TREASURY",
            "arca_class": "CAIXA",
            "fixed_income_term": {
                "instrument_kind": "TESOURO_PRE",
                "indexer": "PRE",
                "contracted_rate": "0.1526",
                "maturity_date": MATURITY.isoformat(),
                "issuer": "Tesouro Nacional",
                **term,
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _buy(api: SimpleNamespace, asset_id: int, unit_price: float) -> None:
    resp = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": PURCHASE.isoformat(),
            "quantity": "2.45",
            "unit_price": str(unit_price),
        },
    )
    assert resp.status_code == 201, resp.text


def _position(api: SimpleNamespace, asset_id: int) -> dict:
    report = api.client.get("/api/v1/portfolio", params={"as_of_date": AS_OF.isoformat()})
    assert report.status_code == 200, report.text
    return next(p for p in report.json()["positions"] if p["asset_id"] == asset_id)


def test_treasury_without_issue_date_accrues_at_the_purchase_rate(api: SimpleNamespace) -> None:
    asset_id = _create_prefixado(api, "Tesouro Prefixado 2029")
    stored = api.client.get(f"/api/v1/assets/{asset_id}").json()["fixed_income_term"]
    assert stored["issue_date"] is None
    assert stored["semiannual_coupons"] is False

    price = _ltn_price(0.1375)
    _buy(api, asset_id, price)
    details = _position(api, asset_id)["fixed_income_details"]

    business_days = len(business_days_between(PURCHASE, AS_OF))
    principal = round(2.45 * price, 2)
    expected = principal * (1.1375 ** (business_days / 252.0) - 1.0)
    assert abs(details["gross_yield"] - expected) < 0.05


def test_issue_date_after_the_purchase_does_not_change_the_valuation(
    api: SimpleNamespace,
) -> None:
    registered = _create_prefixado(api, "Tesouro Prefixado 2029", issue_date=AS_OF.isoformat())
    blank = _create_prefixado(api, "Tesouro Prefixado 2029 B")
    price = _ltn_price(0.1375)
    _buy(api, registered, price)
    _buy(api, blank, price)

    assert (
        _position(api, registered)["fixed_income_details"]
        == _position(api, blank)["fixed_income_details"]
    )


def _create_ipca(api: SimpleNamespace, name: str, rate: str) -> int:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "name": name,
            "asset_type": "TREASURY",
            "arca_class": "CAIXA",
            "fixed_income_term": {
                "instrument_kind": "TESOURO_IPCA",
                "indexer": "IPCA",
                "contracted_rate": rate,
                "maturity_date": "2032-08-15",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_ipca_since_2000(api: SimpleNamespace) -> None:
    points = [
        (date(year, month, 1), 0.4)
        for year in range(2000, 2027)
        for month in range(1, 13)
        if (2000, 7) <= (year, month) <= (2026, 9)
    ]
    with api.uow_factory() as uow:
        uow.market_series.upsert_points("IPCA", points, unit=SeriesUnit.PERCENT_PER_MONTH)
        uow.commit()


def _ipca_details(api: SimpleNamespace) -> tuple[dict, dict]:
    low = _create_ipca(api, "Tesouro IPCA+ 2032", "0.05")
    high = _create_ipca(api, "Tesouro IPCA+ 2032 B", "0.10")
    for asset_id in (low, high):
        _buy(api, asset_id, 2944.70)
    return (
        _position(api, low)["fixed_income_details"],
        _position(api, high)["fixed_income_details"],
    )


def test_ipca_bond_accrues_at_the_rate_implied_by_the_vna(api: SimpleNamespace) -> None:
    _seed_ipca_since_2000(api)

    low, high = _ipca_details(api)

    assert low == high
    assert low["gross_yield"] > 0


def test_ipca_bond_without_ipca_history_uses_the_contracted_rate(api: SimpleNamespace) -> None:
    low, high = _ipca_details(api)

    assert low["gross_value"] < high["gross_value"]


def test_script_00020_makes_issue_date_optional_and_flags_semiannual_bonds(
    tmp_path: Path,
) -> None:
    db_url = f"sqlite:///{(tmp_path / 'fi_mig.db').as_posix()}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    try:
        command.upgrade(cfg, "script_00019")
        with engine.begin() as conn:
            for asset_id, name in (
                (1, "Tesouro Prefixado com Juros Semestrais 2035"),
                (2, "Tesouro Prefixado 2029"),
            ):
                conn.execute(
                    text(
                        "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                        "use_cerrado, is_active, purpose, created_at, updated_at) VALUES "
                        "(:id, :ticker, :name, 'TREASURY', 'CAIXA', 'BRL', 1, 1, 'ARCA', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": asset_id, "ticker": f"T{asset_id}", "name": name},
                )
                conn.execute(
                    text(
                        "INSERT INTO fixed_income_terms (asset_id, instrument_kind, indexer, "
                        "contracted_rate, issue_date, tax_exempt, liquidity) VALUES "
                        "(:id, 'TESOURO_PRE', 'PRE', 0.13, '2026-10-26', 0, 'AT_MATURITY')"
                    ),
                    {"id": asset_id},
                )

        command.upgrade(cfg, "script_00020")
        columns = {c["name"]: c for c in inspect(engine).get_columns("fixed_income_terms")}
        assert columns["issue_date"]["nullable"] is True
        with engine.connect() as conn:
            flags = dict(
                conn.execute(
                    text("SELECT asset_id, semiannual_coupons FROM fixed_income_terms")
                ).all()
            )
        assert {k: bool(v) for k, v in flags.items()} == {1: True, 2: False}

        command.downgrade(cfg, "script_00019")
        columns = {c["name"]: c for c in inspect(engine).get_columns("fixed_income_terms")}
        assert "semiannual_coupons" not in columns
        assert columns["issue_date"]["nullable"] is False
    finally:
        engine.dispose()
