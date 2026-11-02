"""Use cases of the position check (Phase 48.R5): preview, save, list and resolve.

Nothing here writes to the ledger; saving only keeps the check (date, file, lines) so the
Início and the Carteira can say when the position was last confirmed against the B3.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import replace
from datetime import UTC, date, datetime

from core.errors import NotFoundError, ValidationError
from domain.reconciliation.entities import (
    LineResolution,
    PositionReconciliation,
    ReconciliationLine,
)
from domain.reconciliation.reconciler import reconcile
from domain.reconciliation.statement import date_in_file_name, parse_position_statement
from domain.shared.unit_of_work import UoWFactory

MAX_STATEMENT_BYTES = 5 * 1024 * 1024
Sheets = list[tuple[str, list[list[object]]]]


def read_statement_sheets(filename: str, content: bytes) -> Sheets:
    """Every sheet of the .xlsx (one per product), or the single table of a .csv."""
    if len(content) > MAX_STATEMENT_BYTES:
        raise ValidationError("Statement larger than 5 MB", code="FILE_TOO_LARGE")
    name = filename.lower()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ValidationError("Unreadable spreadsheet", code="INVALID_FILE") from exc
        sheets: Sheets = []
        for sheet in book.worksheets:
            # B3 exports declare a stale dimension; scan the actual rows (see the B3 import).
            sheet.reset_dimensions()
            sheets.append((sheet.title, [list(r) for r in sheet.iter_rows(values_only=True)]))
        return sheets
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else ",", delimiters=";,\t")
        return [("Posição", [list(r) for r in csv.reader(io.StringIO(text), dialect)])]
    raise ValidationError(
        "Send the .xlsx (or .csv) Posição statement exported by B3", code="INVALID_FILE"
    )


def _reference(filename: str, given: date | None) -> date:
    found = given or date_in_file_name(filename)
    if found is None:
        raise ValidationError(
            "Informe a data-base da posição (o nome do arquivo da B3 não a trouxe).",
            code="REFERENCE_DATE_REQUIRED",
        )
    if found > date.today():
        raise ValidationError("A data-base não pode estar no futuro.", code="REFERENCE_DATE_FUTURE")
    return found


class ReconciliationHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def preview(
        self, filename: str, content: bytes, reference_date: date | None = None
    ) -> PositionReconciliation:
        """Statement x ledger on the reference date; nothing is saved."""
        on = _reference(filename, reference_date)
        sheets = read_statement_sheets(filename, content)
        try:
            positions = parse_position_statement(sheets)
        except ValueError as exc:
            raise ValidationError(str(exc), code="INVALID_STATEMENT") from exc
        with self.uow_factory() as uow:
            assets = uow.assets.list_all(active_only=False)
            accounts = uow.accounts.list_all()
        return PositionReconciliation(
            reference_date=on,
            file_name=filename,
            file_hash=hashlib.sha256(content).hexdigest(),
            lines=reconcile(positions, assets, accounts, on),
        )

    def commit(
        self, filename: str, content: bytes, reference_date: date | None = None
    ) -> PositionReconciliation:
        """Save the check; the same file for the same date is returned, not duplicated."""
        checked = self.preview(filename, content, reference_date)
        with self.uow_factory() as uow:
            existing = uow.reconciliations.find(checked.reference_date, checked.file_hash)
            if existing is not None:
                return existing
            saved = uow.reconciliations.add(replace(checked, created_at=datetime.now(UTC)))
            uow.commit()
        return saved

    def list_recent(self, limit: int = 20) -> list[PositionReconciliation]:
        with self.uow_factory() as uow:
            return uow.reconciliations.list_recent(limit)

    def get(self, reconciliation_id: int) -> PositionReconciliation:
        with self.uow_factory() as uow:
            found = uow.reconciliations.get(reconciliation_id)
        if found is None:
            raise NotFoundError(f"Reconciliation id={reconciliation_id} not found")
        return found

    def resolve(
        self,
        reconciliation_id: int,
        line_id: int,
        resolution: LineResolution,
        note: str | None = None,
    ) -> ReconciliationLine:
        """Mark a line as explained (or open it again); the ledger is not touched."""
        with self.uow_factory() as uow:
            found = uow.reconciliations.get(reconciliation_id)
            line = next((ln for ln in (found.lines if found else []) if ln.id == line_id), None)
            if line is None:
                raise NotFoundError(
                    f"Line id={line_id} of reconciliation {reconciliation_id} not found"
                )
            resolved = resolution == LineResolution.RESOLVED
            updated = uow.reconciliations.update_line(
                replace(
                    line,
                    resolution=resolution,
                    resolution_note=(note or "").strip() or None,
                    resolved_at=datetime.now(UTC) if resolved else None,
                )
            )
            uow.commit()
        return updated
