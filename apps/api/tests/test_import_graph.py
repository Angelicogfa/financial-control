"""Every module in apps/api must import on its own (guards against circular imports)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
SOURCES = [
    API_DIR / "core",
    API_DIR / "infra",
    API_DIR / "domain",
    API_DIR / "controllers",
    API_DIR / "worker",
]

CHECK = """
import importlib, sys
failures = []
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append(f"{name}: {type(exc).__name__}: {exc}")
if failures:
    print(chr(10).join(failures))
    sys.exit(1)
"""


def _modules() -> list[str]:
    names = ["main", "composition"]
    for src in SOURCES:
        pkg_name = src.name
        for path in sorted(src.rglob("*.py")):
            if "migrations" in path.parts:
                continue
            parts = path.relative_to(src).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mod_name = f"{pkg_name}." + ".".join(parts) if parts else pkg_name
            if mod_name not in names:
                names.append(mod_name)
    return names


def test_each_module_imports_cold() -> None:
    modules = _modules()
    assert "domain.policy.services.policy" in modules
    result = subprocess.run(
        [sys.executable, "-c", CHECK, *modules],
        capture_output=True,
        text=True,
        cwd=str(API_DIR),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
