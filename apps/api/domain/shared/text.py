"""Text helpers for the Portuguese messages shown to the user."""

from __future__ import annotations


def plural(count: int, one: str, many: str) -> str:
    """ "1 ativo" / "3 ativos": the count with the right noun phrase, never "ativo(s)"."""
    return f"{count} {one if count == 1 else many}"
