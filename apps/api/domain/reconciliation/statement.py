"""Reader of the B3 Área do Investidor "Posição" statement (Phase 48.R5).

The export has one sheet per product (Ações, BDR, ETF, Fundo de Investimento, Renda Fixa,
Tesouro Direto…), each with a header row and a "Total" line at the end. The parser is pure:
it receives each sheet as rows of cells and returns the positions it found, with the trading
code when the product has one.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

from domain.reconciliation.entities import StatementPosition

# Same trading code rules as the Negociação/Movimentação import (fractional "F" folded).
TICKER = re.compile(r"^([A-Z0-9]{4,6}\d{0,2})\b")
FRACTIONAL_SUFFIX = re.compile(r"^([A-Z0-9]{4}\d{1,2})F$")
FILE_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def norm(text: object) -> str:
    raw = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(raw.lower().split())


def trading_code(value: object) -> str | None:
    text = str(value or "").strip().upper()
    match = TICKER.match(text.split(" - ")[0].strip()) if text else None
    if not match:
        return None
    ticker = match.group(1)
    fractional = FRACTIONAL_SUFFIX.match(ticker)
    return fractional.group(1) if fractional else ticker


def quantity(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "")
    if text in ("", "-"):
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def date_in_file_name(name: str) -> date | None:
    """`posicao-2026-10-31.xlsx` -> 2026-10-31 (the B3 export names the file by its date)."""
    match = FILE_DATE.search(name or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _header_index(rows: Sequence[Sequence[object]]) -> int | None:
    for i, row in enumerate(rows[:10]):
        names = {norm(c) for c in row}
        if "quantidade" in names and ({"produto", "codigo de negociacao"} & names):
            return i
    return None


def _cell(row: Mapping[str, object], *names: str) -> object:
    for name in names:
        for key, value in row.items():
            if norm(key) == name:
                return value
    return None


def parse_sheet(product: str, rows: Sequence[Sequence[object]]) -> list[StatementPosition]:
    header = _header_index(rows)
    if header is None:
        return []
    names = [str(c or "").strip() for c in rows[header]]
    positions: list[StatementPosition] = []
    for raw in rows[header + 1 :]:
        cells = list(raw)
        if not any(c not in (None, "") for c in cells):
            continue
        first = norm(cells[0] if cells else "")
        if first.startswith("total"):
            continue
        row = dict(zip(names, cells, strict=False))
        qty = quantity(_cell(row, "quantidade"))
        if qty is None:
            continue
        code = _cell(row, "codigo de negociacao")
        description = str(_cell(row, "produto") or code or "").strip()
        institution = _cell(row, "instituicao")
        positions.append(
            StatementPosition(
                product=product.strip() or "Posição",
                description=description,
                quantity=qty,
                ticker=trading_code(code) if code else None,
                institution=str(institution).strip() if institution else None,
            )
        )
    return positions


def parse_position_statement(
    sheets: Iterable[tuple[str, Sequence[Sequence[object]]]],
) -> list[StatementPosition]:
    """Every position of every sheet; sheets without a position header are skipped."""
    found: list[StatementPosition] = []
    for name, rows in sheets:
        found.extend(parse_sheet(name, rows))
    if not found:
        raise ValueError("Not a B3 Posição statement (no sheet with Produto and Quantidade)")
    return found
