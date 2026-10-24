"""Every module must import on its own, in any order (guards against circular imports).

Found in the phase 10 smoke run: Alembic imported `fincontrol_core.policy` first and hit a
cycle that the test suite never saw because other modules were already loaded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [
    ROOT / "packages/config/src",
    ROOT / "packages/core/src",
    ROOT / "packages/persistence/src",
    ROOT / "apps/api/src",
    ROOT / "apps/worker/src",
]

CHECK = """
import importlib, sys
failures = []
for name in sys.argv[1:]:
    for loaded in [m for m in sys.modules if m.startswith("fincontrol_")]:
        del sys.modules[loaded]
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append(f"{name}: {type(exc).__name__}: {exc}")
print(chr(10).join(failures))
sys.exit(1 if failures else 0)
"""


def _modules() -> list[str]:
    names = []
    for src in SOURCES:
        for path in sorted(src.rglob("*.py")):
            parts = path.relative_to(src).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts and parts[-1] != "__main__":
                names.append(".".join(parts))
    return names


def test_each_module_imports_cold() -> None:
    modules = _modules()
    assert "fincontrol_core.policy.models" in modules
    result = subprocess.run(
        [sys.executable, "-c", CHECK, *modules], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
