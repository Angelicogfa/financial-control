"""Layer import contracts (Phase 48.R0, REFACTORING_PLAN.md section 2.1).

Each layer may only import the layers allowed below. The violations that existed when the
contract was introduced live in `architecture_allowlist.py`; that list can only shrink:
a new violation fails, and an allowlisted import that no longer exists fails too, so the
entry is removed in the same change that fixes it (Phase 48.R1 empties it).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture_allowlist import ALLOWED_VIOLATIONS

API_DIR = Path(__file__).resolve().parents[1]

# layer -> package prefixes it must never import.
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "core": ("domain", "infra", "controllers", "worker"),
    "domain": ("controllers", "infra", "worker"),
    "controllers": ("infra.data", "worker"),
    "infra": ("controllers", "worker"),
    "worker": ("controllers",),
}


def _module_name(path: Path, root: Path) -> str:
    parts = path.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(source: str) -> set[str]:
    """Absolute imports anywhere in the module, including lazy ones inside functions."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def _is_under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def find_violations(api_dir: Path = API_DIR) -> dict[str, set[str]]:
    """Map each offending module to the forbidden modules it imports."""
    violations: dict[str, set[str]] = {}
    for layer, forbidden in FORBIDDEN.items():
        for path in sorted((api_dir / layer).rglob("*.py")):
            if "migrations" in path.parts:
                continue
            imported = _imported_modules(path.read_text(encoding="utf-8"))
            bad = {name for name in imported if any(_is_under(name, p) for p in forbidden)}
            if bad:
                violations[_module_name(path, api_dir)] = bad
    return violations


def _pairs(mapping: dict[str, set[str]] | dict[str, frozenset[str]]) -> set[tuple[str, str]]:
    return {(module, target) for module, targets in mapping.items() for target in targets}


def test_no_new_layer_violations() -> None:
    new = sorted(_pairs(find_violations()) - _pairs(ALLOWED_VIOLATIONS))
    assert not new, "imports that break the layer contract:\n" + "\n".join(
        f"  {module} -> {target}" for module, target in new
    )


def test_allowlist_only_shrinks() -> None:
    stale = sorted(_pairs(ALLOWED_VIOLATIONS) - _pairs(find_violations()))
    assert not stale, "fixed violations still allowlisted (remove them):\n" + "\n".join(
        f"  {module} -> {target}" for module, target in stale
    )


def test_allowlisted_modules_belong_to_a_checked_layer() -> None:
    assert all(module.split(".")[0] in FORBIDDEN for module in ALLOWED_VIOLATIONS)


def test_detects_forbidden_imports(tmp_path: Path) -> None:
    pkg = tmp_path / "domain" / "sample"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service.py").write_text(
        "from domain.shared import entities\n"
        "from controllers.sample.responses import SampleDTO\n"
        "def lazy():\n"
        "    import infra.providers.stored\n"
        "from . import sibling\n",
        encoding="utf-8",
    )
    (tmp_path / "controllers").mkdir()
    (tmp_path / "controllers" / "router.py").write_text(
        "from infra.data.unit_of_work import SqlAlchemyUnitOfWork\nfrom infra.cache import x\n",
        encoding="utf-8",
    )

    assert find_violations(tmp_path) == {
        "domain.sample.service": {"controllers.sample.responses", "infra.providers.stored"},
        "controllers.router": {"infra.data.unit_of_work"},
    }


def test_prefix_match_is_by_package_not_by_text() -> None:
    assert _is_under("infra.data", "infra.data")
    assert _is_under("infra.data.health", "infra.data")
    assert not _is_under("infra.database_tools", "infra.data")
