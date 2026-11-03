"""Write the versioned OpenAPI snapshot (Phase 48.R0).

    uv run python scripts/update_openapi_snapshot.py

`apps/api/tests/test_openapi_snapshot.py` fails whenever the API contract changes. Run this
only when the change is intended (a new endpoint or DTO field), never during Phase 48.R1,
whose OpenAPI diff must stay zero. Regenerate `apps/web/src/api/types.ts` too
(`scripts/gen_web_types.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from main import create_app

SNAPSHOT = (
    Path(__file__).resolve().parents[1] / "apps" / "api" / "tests" / "snapshots" / "openapi.json"
)


def render(schema: dict[str, Any]) -> str:
    """Canonical text: sorted keys, stable indentation, trailing newline."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    schema = create_app().openapi()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(render(schema), encoding="utf-8", newline="\n")
    print(f"wrote {SNAPSHOT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
