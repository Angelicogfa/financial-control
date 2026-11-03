"""The API contract is frozen in a versioned OpenAPI snapshot (Phase 48.R0).

A failure here means a route, parameter or DTO changed. If the change is intended, run
`uv run python scripts/update_openapi_snapshot.py` and commit the new snapshot with it;
during Phase 48.R1 the diff must stay zero.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from main import create_app

SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "openapi.json"
MAX_DIFF_LINES = 80


def _render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_openapi_matches_snapshot() -> None:
    current = _render(create_app().openapi())
    stored = SNAPSHOT.read_text(encoding="utf-8")
    if current == stored:
        return
    diff = list(
        difflib.unified_diff(
            stored.splitlines(), current.splitlines(), "snapshot", "current", lineterm=""
        )
    )
    shown = "\n".join(diff[:MAX_DIFF_LINES])
    more = f"\n... {len(diff) - MAX_DIFF_LINES} more lines" if len(diff) > MAX_DIFF_LINES else ""
    raise AssertionError(
        "OpenAPI contract changed; if intended, run scripts/update_openapi_snapshot.py\n"
        + shown
        + more
    )


def test_openapi_is_deterministic() -> None:
    assert _render(create_app().openapi()) == _render(create_app().openapi())


def test_snapshot_is_canonical() -> None:
    stored = SNAPSHOT.read_text(encoding="utf-8")
    assert stored == _render(json.loads(stored))


def test_schema_names_are_unique_across_contexts() -> None:
    """Two schemas of different contexts with the same class name collide in the OpenAPI: one
    silently replaces the other (Phase 48.R8 caught a second `AssetForecastDTO`). Identical
    copies (same fields) are harmless and predate this guard."""
    import ast

    contracts = Path(__file__).resolve().parents[1] / "contracts"
    seen: dict[str, tuple[str, str]] = {}
    duplicates: list[str] = []
    for path in sorted(contracts.rglob("*.py")):
        context = path.relative_to(contracts).parts[0]
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef):
                shape = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                first_context, first_shape = seen.setdefault(node.name, (context, shape))
                if first_context != context and first_shape != shape:
                    duplicates.append(f"{node.name}: {first_context} and {context}")
    assert not duplicates, duplicates
