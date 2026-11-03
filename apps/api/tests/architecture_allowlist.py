"""Layer violations tolerated by the import contract (`test_architecture_contracts.py`).

Phase 48.R0 started it with the 29 modules / 118 imports that predated the contract; Phase
48.R1 emptied it. It stays empty: fix the import instead of adding an entry.
"""

from __future__ import annotations

ALLOWED_VIOLATIONS: dict[str, frozenset[str]] = {}
