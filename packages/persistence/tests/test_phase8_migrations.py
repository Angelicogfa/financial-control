"""Integration tests for the phase 8 data migrations (script_00002 onwards)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

PERSISTENCE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path: Path) -> tuple[Config, Engine]:
    db_url = f"sqlite:///{(tmp_path / 'phase8_migrations.db').as_posix()}"
    cfg = Config(str(PERSISTENCE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    yield cfg, engine
    engine.dispose()


def test_script_00002_tags_existing_series_with_units(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00001")
    with engine.begin() as conn:
        for symbol, value in (
            ("CDI", 0.0393),
            ("SELIC", 0.0393),
            ("IPCA", 0.16),
            ("IBOV", 120000.0),
            ("WEGE3", 52.0),
        ):
            conn.execute(
                text(
                    "INSERT INTO market_series (symbol, reference_date, value) "
                    "VALUES (:s, '2025-01-02', :v)"
                ),
                {"s": symbol, "v": value},
            )

    command.upgrade(cfg, "script_00002")

    with engine.connect() as conn:
        units = dict(conn.execute(text("SELECT symbol, unit FROM market_series")).all())
    assert units == {
        "CDI": "PERCENT_PER_DAY",
        "SELIC": "PERCENT_PER_DAY",
        "IPCA": "PERCENT_PER_MONTH",
        "IBOV": "INDEX_POINTS",
        "WEGE3": "PRICE",
    }

    command.downgrade(cfg, "script_00001")
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(market_series)"))]
    assert "unit" not in columns


def test_script_00003_normalizes_percent_scaled_contracted_rates(
    db: tuple[Config, Engine],
) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00002")
    rows = [
        (1, "CDI", 110.0),
        (2, "CDI", 1.10),
        (3, "SELIC", 100.0),
        (4, "IPCA", 6.5),
        (5, "IPCA", 0.065),
        (6, "PRE", 12.0),
    ]
    with engine.begin() as conn:
        for asset_id, indexer, rate in rows:
            conn.execute(
                text(
                    "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                    "cerrado_answers, created_at, updated_at) VALUES (:id, :t, :t, "
                    "'FIXED_INCOME', 'CAIXA', 'BRL', '{}', '2025-01-01', '2025-01-01')"
                ),
                {"id": asset_id, "t": f"RF-{asset_id}"},
            )
            conn.execute(
                text(
                    "INSERT INTO fixed_income_terms (asset_id, instrument_kind, indexer, "
                    "contracted_rate, issue_date, tax_exempt, liquidity) VALUES "
                    "(:id, 'CDB', :ix, :rate, '2025-01-02', 0, 'AT_MATURITY')"
                ),
                {"id": asset_id, "ix": indexer, "rate": rate},
            )

    command.upgrade(cfg, "script_00003")

    with engine.connect() as conn:
        rates = {
            asset_id: float(rate)
            for asset_id, rate in conn.execute(
                text("SELECT asset_id, contracted_rate FROM fixed_income_terms")
            )
        }
    assert rates == {
        1: pytest.approx(1.10),
        2: pytest.approx(1.10),
        3: pytest.approx(1.00),
        4: pytest.approx(0.065),
        5: pytest.approx(0.065),
        6: pytest.approx(0.12),
    }
