"""Migration rehearsal on a restored copy of the real database (Phase 48.R0).

    python -m infra.data.migration_rehearsal --url postgresql+psycopg://...

`scripts/migration_rehearsal.sh` restores a dump of `fincontrol_pgdata` into a throwaway
Postgres and runs this against it; never point it at the real database. It checks the rule
of the refactoring plan: migrations are additive only. Every table and column that existed
before must still exist after `upgrade head`, and no table may lose rows. The last step
proves the way back: downgrade to the starting revision (or one step below head when nothing
is pending) and upgrade again, ending on the same schema.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text

API_DIR = Path(__file__).resolve().parents[2]
VERSION_TABLE = "alembic_version"


@dataclass(frozen=True)
class SchemaSnapshot:
    revision: str | None
    columns: dict[str, frozenset[str]]
    row_counts: dict[str, int]


@dataclass
class RehearsalReport:
    start_revision: str | None
    head_revision: str
    roundtrip_revision: str | None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def take_snapshot(engine: Engine) -> SchemaSnapshot:
    inspector = inspect(engine)
    tables = sorted(t for t in inspector.get_table_names() if t != VERSION_TABLE)
    columns = {t: frozenset(c["name"] for c in inspector.get_columns(t)) for t in tables}
    preparer = engine.dialect.identifier_preparer
    with engine.connect() as conn:
        counts = {
            t: int(conn.execute(text(f"SELECT COUNT(*) FROM {preparer.quote(t)}")).scalar_one())
            for t in tables
        }
        revision = None
        if VERSION_TABLE in inspector.get_table_names():
            revision = conn.execute(text(f"SELECT version_num FROM {VERSION_TABLE}")).scalar()
    return SchemaSnapshot(revision=revision, columns=columns, row_counts=counts)


def additive_problems(before: SchemaSnapshot, after: SchemaSnapshot) -> list[str]:
    """What `after` lost compared to `before`: tables, columns or rows."""
    problems: list[str] = []
    for table, cols in before.columns.items():
        if table not in after.columns:
            problems.append(f"table dropped: {table}")
            continue
        for col in sorted(cols - after.columns[table]):
            problems.append(f"column dropped: {table}.{col}")
        old, new = before.row_counts[table], after.row_counts[table]
        if new < old:
            problems.append(f"rows lost: {table} ({old} -> {new})")
    return problems


def schema_differences(expected: SchemaSnapshot, actual: SchemaSnapshot) -> list[str]:
    diffs = [f"missing table: {t}" for t in sorted(set(expected.columns) - set(actual.columns))]
    diffs += [f"extra table: {t}" for t in sorted(set(actual.columns) - set(expected.columns))]
    for table in sorted(set(expected.columns) & set(actual.columns)):
        if expected.columns[table] != actual.columns[table]:
            diffs.append(f"columns differ: {table}")
    return diffs


def rehearse(cfg: Config, engine: Engine) -> RehearsalReport:
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("no migrations found")
    before = take_snapshot(engine)
    if before.revision is None:
        raise RuntimeError("the database has no alembic_version: restore a real dump first")

    pending = before.revision != head
    if pending:
        roundtrip = before.revision
    else:
        down = ScriptDirectory.from_config(cfg).get_revision(head).down_revision
        roundtrip = down if isinstance(down, str) else None
    report = RehearsalReport(before.revision, head, roundtrip)

    command.upgrade(cfg, "head")
    after = take_snapshot(engine)
    report.problems += additive_problems(before, after)
    if roundtrip is None:
        return report

    command.downgrade(cfg, roundtrip)
    middle = take_snapshot(engine)
    if pending:
        report.problems += [f"downgrade: {d}" for d in schema_differences(before, middle)]
    command.upgrade(cfg, "head")
    final = take_snapshot(engine)
    report.problems += [f"re-upgrade: {p}" for p in additive_problems(middle, final)]
    report.problems += [f"re-upgrade: {d}" for d in schema_differences(after, final)]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="SQLAlchemy URL of the restored copy")
    args = parser.parse_args(argv)
    engine = create_engine(args.url, future=True)
    try:
        report = rehearse(alembic_config(args.url), engine)
    finally:
        engine.dispose()
    print(f"start {report.start_revision} -> head {report.head_revision}")
    print(f"round trip through {report.roundtrip_revision or '(none)'}")
    for problem in report.problems:
        print(f"PROBLEM {problem}")
    print("REHEARSAL OK" if report.ok else "REHEARSAL FAILED")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
