"""Statement x ledger, per ticker and custody account (Phase 48.R5). Pure.

Accounts: B3 names the institution ("XP INVESTIMENTOS CCTVM S/A"); an account matches when the
words of its institution (or, without one, of its name) are all in it. Ledger quantities of
accounts that no statement institution matched, and statement rows of institutions that match
no account, are compared together under "no account", so a one-broker investor without
institutions set up still gets a line per ticker.

Only B3-listed assets are compared: the statement gives Tesouro Direto and bank fixed income
by product, without a trading code, and the ledger keeps their value, not units.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.reconciliation.entities import (
    LineStatus,
    ReconciliationLine,
    StatementPosition,
)
from domain.reconciliation.statement import norm, trading_code
from domain.shared.entities import AccountEntity, AssetEntity
from domain.shared.enums import Market

ZERO = Decimal("0")
TOLERANCE = Decimal("0.000001")
# Words that say nothing about which institution it is.
_NOISE = frozenset(
    {"s/a", "sa", "s.a.", "cctvm", "dtvm", "ctvm", "de", "e", "do", "da", "ltda", "banco"}
)


def _words(text: str | None) -> set[str]:
    return {w for w in norm(text).replace(",", " ").split() if w not in _NOISE}


def match_account(
    institution: str | None, accounts: Iterable[AccountEntity]
) -> AccountEntity | None:
    """The one account whose institution words are all in the B3 institution name."""
    found = _words(institution)
    if not found:
        return None
    matches = [a for a in accounts if (words := _words(a.institution or a.name)) and words <= found]
    return matches[0] if len(matches) == 1 else None


def _ledger_by_account(asset: AssetEntity, on: date) -> tuple[dict[int | None, Decimal], str]:
    """Quantity held on `on` in each account; a ledger that sells more than it has reads 0."""
    accounts = {t.account_id for t in asset.transactions}
    held: dict[int | None, Decimal] = {}
    note = ""
    for account_id in accounts:
        trades = [t for t in asset.transactions if t.account_id == account_id]
        try:
            qty = build_position(trades, up_to_date=on, events=asset.corporate_events).quantity
        except InsufficientQuantityError:
            qty = ZERO
            note = "O livro vende mais do que tinha nesta conta; corrija os lançamentos."
        if qty > ZERO:
            held[account_id] = qty
    return held, note


def _status(b3: Decimal, ledger: Decimal) -> LineStatus:
    if abs(b3 - ledger) <= TOLERANCE:
        return LineStatus.MATCH
    if ledger <= ZERO:
        return LineStatus.ONLY_B3
    if b3 <= ZERO:
        return LineStatus.ONLY_LEDGER
    return LineStatus.DIVERGENT


def reconcile(
    positions: Iterable[StatementPosition],
    assets: Iterable[AssetEntity],
    accounts: Iterable[AccountEntity],
    reference_date: date,
) -> list[ReconciliationLine]:
    accounts = list(accounts)
    by_ticker = {a.ticker: a for a in assets if a.market == Market.B3}
    names = {a.id: a.name for a in accounts}

    lines: list[ReconciliationLine] = []
    statement: dict[tuple[str, int | None], Decimal] = defaultdict(lambda: ZERO)
    product: dict[str, str] = {}
    institutions: dict[tuple[str, int | None], set[str]] = defaultdict(set)
    mapped: set[int] = set()
    for p in positions:
        if not p.ticker:
            lines.append(
                ReconciliationLine(
                    product=p.product,
                    b3_quantity=p.quantity,
                    ledger_quantity=ZERO,
                    status=LineStatus.NOT_COMPARED,
                    institution=p.institution,
                    note=f"{p.description}: sem código de negociação, conferido só pelo valor.",
                )
            )
            continue
        account = match_account(p.institution, accounts)
        key = (trading_code(p.ticker) or p.ticker, account.id if account else None)
        if account and account.id is not None:
            mapped.add(account.id)
        statement[key] += p.quantity
        product.setdefault(key[0], p.product)
        if p.institution:
            institutions[key].add(p.institution)

    ledger: dict[tuple[str, int | None], Decimal] = defaultdict(lambda: ZERO)
    notes: dict[str, str] = {}
    for ticker, asset in by_ticker.items():
        held, note = _ledger_by_account(asset, reference_date)
        if note:
            notes[ticker] = note
        for account_id, qty in held.items():
            ledger[(ticker, account_id if account_id in mapped else None)] += qty

    for key in sorted(set(statement) | set(ledger), key=lambda k: (k[0], k[1] or 0)):
        ticker, account_id = key
        b3, own = statement.get(key, ZERO), ledger.get(key, ZERO)
        if b3 <= ZERO and own <= ZERO:
            continue
        asset = by_ticker.get(ticker)
        status = _status(b3, own)
        note = notes.get(ticker, "")
        if status == LineStatus.ONLY_B3 and asset is None:
            note = note or "Ativo não cadastrado: cadastre-o e lance a compra."
        lines.append(
            ReconciliationLine(
                product=product.get(ticker, "Ações"),
                b3_quantity=b3,
                ledger_quantity=own,
                status=status,
                ticker=ticker,
                asset_id=asset.id if asset else None,
                account_id=account_id,
                institution=", ".join(sorted(institutions[key]))
                or (names.get(account_id) if account_id is not None else None),
                note=note,
            )
        )
    return lines
