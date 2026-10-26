"""Tests for the demonstration data seed (item 14.1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fincontrol_core.domain.entities import AssetEntity
from fincontrol_core.domain.enums import AssetType
from fincontrol_core.errors import ConflictError
from fincontrol_core.market.models import Quote
from fincontrol_core.policy import current_policy
from fincontrol_core.portfolio.consolidation import LEDGER_VALID, consolidate_portfolio
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.seed_demo import MARKET_ASSETS, main, seed_demo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def uow_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'demo.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


def test_seed_builds_a_valid_portfolio_with_history(uow_factory: UoWFactory) -> None:
    summary = seed_demo(uow_factory, today=date(2026, 3, 10), years=1, seed=1)
    assert summary.assets == len(MARKET_ASSETS) + 4
    assert summary.trades > 60
    assert summary.earnings > 10
    assert summary.snapshots > 200

    with uow_factory() as uow:
        assets = uow.assets.list_all()
        snapshots = uow.snapshots.list_range()
        assert max(s.snapshot_date for s in snapshots) < date(2026, 3, 10)
        assert uow.market_series.date_range("CDI") is not None
        assert uow.market_series.date_range("IBOV") is not None
        report = consolidate_portfolio(
            assets,
            current_policy(uow.policies).arca.targets,
            quotes={s.ticker: Quote(symbol=s.ticker, price=s.end_price) for s in MARKET_ASSETS},
            usd_brl_rate=5.4,
            as_of_date=date(2026, 3, 9),
        )
    assert all(p.ledger_status == LEDGER_VALID for p in report.positions)
    assert report.total_received_earnings_brl > 0
    assert report.value_by_purpose_brl["EMERGENCY_RESERVE"] == pytest.approx(8000)
    assert snapshots[-1].market_value > snapshots[0].market_value  # it grew with contributions


def test_price_paths_are_seeded_and_end_at_the_anchor() -> None:
    import random

    from fincontrol_worker.seed_demo import _price_path

    first = _price_path(random.Random(3), 50, 52.0, 0.1, 0.3)
    again = _price_path(random.Random(3), 50, 52.0, 0.1, 0.3)
    other = _price_path(random.Random(4), 50, 52.0, 0.1, 0.3)
    assert first == again != other
    assert first[-1] == 52.0


def test_seed_runs_only_once(uow_factory: UoWFactory) -> None:
    seed_demo(uow_factory, today=date(2026, 3, 10), years=1, seed=3)
    with pytest.raises(ConflictError):
        seed_demo(uow_factory, today=date(2026, 3, 10), years=1, seed=3)


def test_seed_refuses_a_database_with_assets(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        uow.assets.add(AssetEntity(ticker="MINE3", name="Real", asset_type=AssetType.STOCK_BR))
        uow.commit()
    with pytest.raises(ConflictError) as error:
        seed_demo(uow_factory, today=date(2026, 3, 10))
    assert error.value.code == "DEMO_NOT_EMPTY"
    with uow_factory() as uow:
        assert [a.ticker for a in uow.assets.list_all()] == ["MINE3"]


def test_cli_prints_a_summary(uow_factory: UoWFactory, capsys: pytest.CaptureFixture[str]) -> None:
    main(["--years", "1", "--today", "2026-03-10"])
    assert "Demo ready:" in capsys.readouterr().out
