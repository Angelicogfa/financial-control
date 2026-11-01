"""Migration rehearsal (Phase 48.R0): additive checks and the upgrade/downgrade round trip."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text

from infra.data.migration_rehearsal import (
    SchemaSnapshot,
    additive_problems,
    alembic_config,
    main,
    rehearse,
    schema_differences,
    take_snapshot,
)


@pytest.fixture
def copy_db(tmp_path: Path) -> Iterator[tuple[str, Config, Engine]]:
    url = f"sqlite:///{(tmp_path / 'rehearsal.db').as_posix()}"
    engine = create_engine(url, future=True)
    yield url, alembic_config(url), engine
    engine.dispose()


def _previous_of_head(cfg: Config) -> str:
    script = ScriptDirectory.from_config(cfg)
    down = script.get_revision(script.get_current_head()).down_revision
    assert isinstance(down, str)
    return down


def _seed_series(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO market_series (symbol, reference_date, value, unit) "
                "VALUES ('CDI', '2026-10-30', 0.05, 'PERCENT_PER_DAY')"
            )
        )


def _snap(columns: dict[str, set[str]], rows: dict[str, int]) -> SchemaSnapshot:
    return SchemaSnapshot(
        revision="r", columns={t: frozenset(c) for t, c in columns.items()}, row_counts=rows
    )


def test_additive_problems_flags_dropped_tables_columns_and_lost_rows() -> None:
    before = _snap({"a": {"id", "x"}, "b": {"id"}, "c": {"id"}}, {"a": 3, "b": 1, "c": 5})
    after = _snap({"a": {"id"}, "c": {"id"}, "d": {"id"}}, {"a": 3, "c": 2, "d": 0})

    assert additive_problems(before, after) == [
        "column dropped: a.x",
        "table dropped: b",
        "rows lost: c (5 -> 2)",
    ]


def test_additive_problems_accepts_new_tables_columns_and_rows() -> None:
    before = _snap({"a": {"id"}}, {"a": 1})
    after = _snap({"a": {"id", "note"}, "b": {"id"}}, {"a": 4, "b": 0})

    assert additive_problems(before, after) == []


def test_schema_differences() -> None:
    expected = _snap({"a": {"id"}, "b": {"id"}}, {"a": 0, "b": 0})
    actual = _snap({"a": {"id", "x"}, "c": {"id"}}, {"a": 0, "c": 0})

    assert schema_differences(expected, actual) == [
        "missing table: b",
        "extra table: c",
        "columns differ: a",
    ]


def test_take_snapshot_reads_revision_columns_and_counts(
    copy_db: tuple[str, Config, Engine],
) -> None:
    _, cfg, engine = copy_db
    command.upgrade(cfg, "head")
    _seed_series(engine)

    snap = take_snapshot(engine)

    assert snap.revision == ScriptDirectory.from_config(cfg).get_current_head()
    assert "alembic_version" not in snap.columns
    assert {"symbol", "unit"} <= snap.columns["market_series"]
    assert snap.row_counts["market_series"] == 1


def test_rehearse_pending_migration_keeps_data_and_round_trips(
    copy_db: tuple[str, Config, Engine],
) -> None:
    _, cfg, engine = copy_db
    start = _previous_of_head(cfg)
    command.upgrade(cfg, start)
    _seed_series(engine)

    report = rehearse(cfg, engine)

    assert report.ok, report.problems
    assert report.start_revision == start
    assert report.roundtrip_revision == start
    assert take_snapshot(engine).revision == report.head_revision
    assert take_snapshot(engine).row_counts["market_series"] == 1


def test_rehearse_up_to_date_copy_round_trips_the_head(
    copy_db: tuple[str, Config, Engine],
) -> None:
    _, cfg, engine = copy_db
    command.upgrade(cfg, "head")
    _seed_series(engine)

    report = rehearse(cfg, engine)

    assert report.ok, report.problems
    assert report.start_revision == report.head_revision
    assert report.roundtrip_revision == _previous_of_head(cfg)


def test_rehearse_refuses_a_database_without_alembic_version(
    copy_db: tuple[str, Config, Engine],
) -> None:
    _, cfg, engine = copy_db
    with pytest.raises(RuntimeError, match="alembic_version"):
        rehearse(cfg, engine)


def test_main_reports_ok(
    copy_db: tuple[str, Config, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, cfg, _ = copy_db
    command.upgrade(cfg, _previous_of_head(cfg))

    assert main(["--url", url]) == 0
    assert "REHEARSAL OK" in capsys.readouterr().out
