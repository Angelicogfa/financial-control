"""Integration tests for phase 11 persistence: checklist history and its migration (11.4)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fincontrol_core.domain.entities import (
    AssetEntity,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
)
from fincontrol_core.domain.enums import AnswerSource, AnswerValue, AssetType, ChecklistProfile
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

PERSISTENCE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path: Path) -> Iterator[tuple[Config, Engine]]:
    db_url = f"sqlite:///{(tmp_path / 'phase11.db').as_posix()}"
    cfg = Config(str(PERSISTENCE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    yield cfg, engine
    engine.dispose()


@pytest.fixture
def uow_factory(db: tuple[Config, Engine]) -> Callable[[], SqlAlchemyUnitOfWork]:
    cfg, engine = db
    command.upgrade(cfg, "head")
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


def test_script_00011_moves_cerrado_answers_to_history(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00010")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                "cerrado_answers, created_at, updated_at) VALUES (1, 'WEGE3', 'WEG', "
                "'STOCK_BR', 'ACOES', 'BRL', :answers, '2025-01-01', '2025-03-01')"
            ),
            {"answers": json.dumps({"roe": True, "debt": False, "moat": None})},
        )

    command.upgrade(cfg, "script_00011")

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT question_id, value, source, checklist_version FROM checklist_answers "
                "ORDER BY question_id"
            )
        ).all()
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(assets)"))]
    assert [tuple(r) for r in rows] == [("debt", "NO", "MANUAL", 1), ("roe", "YES", "MANUAL", 1)]
    assert "cerrado_answers" not in columns
    assert "checklist_profile" in columns

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO checklist_answers (asset_id, question_id, value, source, "
                "answered_at, checklist_version) VALUES (1, 'roe', 'NA', 'MANUAL', "
                "'2026-01-01', 2), (1, 'governance', 'YES', 'MANUAL', '2026-01-01', 2)"
            )
        )

    command.downgrade(cfg, "script_00010")
    with engine.connect() as conn:
        legacy = conn.execute(text("SELECT cerrado_answers FROM assets")).scalar()
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master"))}
    assert json.loads(legacy) == {"debt": False, "governance": True}
    assert "checklist_answers" not in tables


def test_answers_are_append_only_and_current_view_is_latest(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    with uow_factory() as uow:
        asset = uow.assets.add(
            AssetEntity(
                ticker="ITUB4",
                name="Itaú",
                asset_type=AssetType.STOCK_BR,
                checklist_profile=ChecklistProfile.BANK,
                cerrado_answers={"basel": True, "npl": "NA"},
            )
        )
        uow.commit()
    assert asset.id is not None

    with uow_factory() as uow:
        current = uow.assets.get_by_id(asset.id)
        assert current is not None
        assert current.checklist_profile == ChecklistProfile.BANK
        # Same values resubmitted without evidence: nothing new is stored.
        uow.assets.update(replace(current, cerrado_answers={"basel": True, "npl": "NA"}))
        uow.commit()
    with uow_factory() as uow:
        assert len(uow.checklists.answer_history(asset.id)) == 2

    with uow_factory() as uow:
        current = uow.assets.get_by_id(asset.id)
        assert current is not None
        changed = {
            "basel": ChecklistAnswer("basel", AnswerValue.NO, evidence="Basileia 10,5% no 3T"),
        }
        saved = uow.assets.update(replace(current, cerrado_answers=changed))
        uow.commit()

    assert {q: a.value for q, a in saved.cerrado_answers.items()} == {"basel": AnswerValue.NO}
    with uow_factory() as uow:
        history = uow.checklists.answer_history(asset.id)
    # Same timestamp: rows are appended in question order, newest id first.
    assert [(a.question_id, a.value) for a in history[:2]] == [
        ("npl", None),
        ("basel", AnswerValue.NO),
    ]
    assert len(history) == 4
    assert history[-1].source == AnswerSource.MANUAL
    assert any(a.evidence == "Basileia 10,5% no 3T" for a in history)


def test_evaluation_history_is_ordered_and_limited(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    with uow_factory() as uow:
        asset = uow.assets.add(AssetEntity(ticker="X", name="X", asset_type=AssetType.CRYPTO))
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for week in range(3):
            uow.checklists.record_evaluation(
                ChecklistEvaluationRecord(
                    asset_id=asset.id or 0,
                    evaluated_at=start + timedelta(weeks=week),
                    profile=ChecklistProfile.CRYPTO,
                    score=week,
                    normalized_score=week / 5,
                    coverage_pct=20.0 * week,
                    answered=week,
                    applicable=5,
                    recommendation="APTO",
                )
            )
        uow.commit()

    with uow_factory() as uow:
        history = uow.checklists.evaluation_history(asset.id or 0)
        assert [r.score for r in history] == [0, 1, 2]
        assert [r.score for r in uow.checklists.evaluation_history(asset.id or 0, limit=2)] == [
            1,
            2,
        ]
        latest = uow.checklists.latest_evaluation(asset.id or 0)
        assert latest is not None and latest.score == 2
        assert uow.checklists.latest_evaluation(999) is None
