"""Financial statements delivered to the CVM (DFP and ITR), point in time (Phase 42.2).

The CVM files share one layout for every company: one CSV row per account, with the code
(`CD_CONTA`), the name, the value, the scale (thousands or units), the version and, in the main
file, the delivery date (`DT_RECEB`). The plan of accounts is fixed at the top levels, but:

- there are three templates: companies, banks and insurers. A code means different things in
  each (2.03 is the equity of a company and the provisions of a bank), so the equity and the
  net income are found by name, and revenue, EBIT, cash and debt are read for companies only;
- depreciation and dividends paid sit in free accounts of the cash flow statement, found by
  name under the operating (6.01.01) and financing (6.03) sections;
- an ITR brings the quarter and the year to date; the year to date is kept (the cash flow has
  only that one) and the trailing twelve months are rebuilt from it and the last annual DFP;
- a statement can be delivered again (versions); each version is kept with its delivery date,
  so a past date sees only what had been delivered by then.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

# --- metrics ------------------------------------------------------------------------------------

REVENUE = "revenue"
EBIT = "ebit"
NET_INCOME = "net_income"  # attributable to the controlling shareholders when split
DEPRECIATION = "depreciation"
DIVIDENDS_PAID = "dividends_paid"
TOTAL_ASSETS = "total_assets"
EQUITY = "equity"
MINORITY_INTEREST = "minority_interest"
CASH = "cash"
SHORT_TERM_INVESTMENTS = "short_term_investments"
DEBT_CURRENT = "debt_current"
DEBT_NONCURRENT = "debt_noncurrent"
SHARES = "shares_outstanding"

FLOW_METRICS = (REVENUE, EBIT, NET_INCOME, DEPRECIATION, DIVIDENDS_PAID)
BALANCE_METRICS = (
    TOTAL_ASSETS,
    EQUITY,
    MINORITY_INTEREST,
    CASH,
    SHORT_TERM_INVESTMENTS,
    DEBT_CURRENT,
    DEBT_NONCURRENT,
    SHARES,
)

COMPANY = "COMPANY"
FINANCIAL = "FINANCIAL"  # banks and insurers: no revenue, EBIT or debt in the company sense

DFP = "DFP"
ITR = "ITR"
CONSOLIDATED = "CON"
INDIVIDUAL = "IND"

LATEST = "ÚLTIMO"  # ORDEM_EXERC of the current period (the other is the comparative)
SCALES = {"MIL": 1000.0, "UNIDADE": 1.0}

_DEPRECIATION = re.compile(r"deprecia|amortiza|exaust")
_NOT_DEPRECIATION = re.compile(
    r"emprestimo|financiament|debenture|captac|custo.{0,4}transac|juros|premio|agio|desagio"
)
_DIVIDENDS = re.compile(r"dividend|juros sobre (o )?capital|\bjcp\b")
_RECEIVED = re.compile(r"recebid")
_EQUITY = re.compile(r"^patrimonio liquido")
_MINORITY = re.compile(r"nao controlador")
_NET_INCOME = re.compile(r"^lucro.*periodo")
_CONTROLLING = re.compile(r"controlador")
_FINANCIAL_REVENUE = re.compile(r"intermedia|seguro|premio|resseguro")


def plain(text: str) -> str:
    """Lower case without accents: the CVM names come with and without them."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()


# --- entities -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatementDoc:
    """A delivered statement: one company, one reference date, one version."""

    cnpj: str
    doc_type: str  # DFP (annual) or ITR (quarterly)
    reference_date: date
    version: int
    delivered_on: date


@dataclass(frozen=True)
class StatementFact:
    """One value of a delivered statement, in reais (shares in units)."""

    cnpj: str
    doc_type: str
    reference_date: date
    version: int
    delivered_on: date
    basis: str  # CON or IND
    template: str  # COMPANY or FINANCIAL
    metric: str
    period_start: date | None  # None for balance-sheet values
    period_end: date
    value: float


@dataclass(frozen=True)
class AccountRow:
    """The part of a CVM account row the extraction needs."""

    cnpj: str
    reference_date: date
    version: int
    order: str
    period_start: date | None
    period_end: date
    code: str
    name: str
    value: float


# --- extraction -----------------------------------------------------------------------------


def _depth(code: str) -> int:
    return code.count(".")


def needed(code: str) -> bool:
    """Whether the extraction reads this account: the statements' top three levels, the
    depreciation lines (children of 6.01.01) and the financing lines (children of 6.03)."""
    if code.startswith("6."):
        return (code.startswith("6.01.01.") and _depth(code) == 3) or (
            code.startswith("6.03.") and _depth(code) == 2
        )
    return _depth(code) <= 2


class _DocAccounts:
    """The accounts of one statement and one basis, current period only."""

    def __init__(self) -> None:
        # code -> (period_start, period_end, name, value); the earliest start wins (year to date).
        self.rows: dict[str, tuple[date | None, date, str, float]] = {}

    def add(self, row: AccountRow) -> None:
        current = self.rows.get(row.code)
        if current is None or (row.period_start or date.max) < (current[0] or date.max):
            self.rows[row.code] = (row.period_start, row.period_end, plain(row.name), row.value)

    def value(self, code: str) -> float | None:
        item = self.rows.get(code)
        return item[3] if item else None

    def name(self, code: str) -> str:
        item = self.rows.get(code)
        return item[2] if item else ""

    def period(self, code: str) -> tuple[date | None, date] | None:
        item = self.rows.get(code)
        return (item[0], item[1]) if item else None

    def children(self, parent: str) -> list[str]:
        prefix = parent + "."
        depth = _depth(parent) + 1
        return [c for c in self.rows if c.startswith(prefix) and _depth(c) == depth]

    def find(self, parent: str, pattern: re.Pattern[str]) -> list[str]:
        return [c for c in self.children(parent) if pattern.search(self.name(c))]


def _equity_code(accounts: _DocAccounts) -> str | None:
    found = accounts.find("2", _EQUITY)
    return found[0] if found else None


def _net_income_code(accounts: _DocAccounts) -> str | None:
    found = sorted(accounts.find("3", _NET_INCOME), key=lambda c: int(c.split(".")[1]))
    if not found:
        return None
    total = found[-1]
    controlling = [
        c
        for c in accounts.children(total)
        if _CONTROLLING.search(accounts.name(c)) and not _MINORITY.search(accounts.name(c))
    ]
    return controlling[0] if controlling else total


def _sum(accounts: _DocAccounts, codes: Iterable[str]) -> float | None:
    values = [abs(v) for c in codes if (v := accounts.value(c)) is not None]
    return float(sum(values)) if values else None


# Above this book value per share the count can only be in thousands: the share-count file has
# no scale column and some companies (Vale, Itaú) fill it in thousands.
MAX_BOOK_VALUE_PER_SHARE = 1000.0


def _shares_in_units(shares: float | None, equity: float | None) -> float | None:
    if shares is None or shares <= 0:
        return None
    if equity is not None and equity > 0 and equity / shares > MAX_BOOK_VALUE_PER_SHARE:
        return shares * 1000.0
    return shares


def extract_facts(
    doc: StatementDoc,
    basis: str,
    accounts_rows: Iterable[AccountRow],
    shares: float | None = None,
) -> list[StatementFact]:
    """The metrics of one delivered statement from its account rows (one basis)."""
    accounts = _DocAccounts()
    for row in accounts_rows:
        if row.order == LATEST:
            accounts.add(row)
    equity_code = _equity_code(accounts)
    if equity_code is not None:
        template = COMPANY if equity_code == "2.03" else FINANCIAL
    else:  # no balance sheet in this file: the revenue line tells a bank or insurer apart
        template = FINANCIAL if _FINANCIAL_REVENUE.search(accounts.name("3.01")) else COMPANY
    out: list[StatementFact] = []

    def put(metric: str, value: float | None, code: str | None) -> None:
        if value is None or code is None:
            return
        period = accounts.period(code)
        if period is None:
            return
        start, end = period
        out.append(
            StatementFact(
                cnpj=doc.cnpj,
                doc_type=doc.doc_type,
                reference_date=doc.reference_date,
                version=doc.version,
                delivered_on=doc.delivered_on,
                basis=basis,
                template=template,
                metric=metric,
                period_start=start if metric in FLOW_METRICS else None,
                period_end=end,
                value=value,
            )
        )

    put(TOTAL_ASSETS, accounts.value("1"), "1")
    if equity_code:
        put(EQUITY, accounts.value(equity_code), equity_code)
        minority = accounts.find(equity_code, _MINORITY)
        if minority:
            put(MINORITY_INTEREST, accounts.value(minority[0]), minority[0])
    income = _net_income_code(accounts)
    if income:
        put(NET_INCOME, accounts.value(income), income)
    if template == COMPANY:
        put(REVENUE, accounts.value("3.01"), "3.01")
        put(EBIT, accounts.value("3.05"), "3.05")
        put(CASH, accounts.value("1.01.01"), "1.01.01")
        put(SHORT_TERM_INVESTMENTS, accounts.value("1.01.02"), "1.01.02")
        put(DEBT_CURRENT, accounts.value("2.01.04"), "2.01.04")
        put(DEBT_NONCURRENT, accounts.value("2.02.01"), "2.02.01")
        depreciation = [
            c
            for c in accounts.children("6.01.01")
            if _DEPRECIATION.search(accounts.name(c))
            and not _NOT_DEPRECIATION.search(accounts.name(c))
        ]
        if depreciation:
            put(DEPRECIATION, _sum(accounts, depreciation), depreciation[0])
    dividends = [
        c
        for c in accounts.children("6.03")
        if _DIVIDENDS.search(accounts.name(c)) and not _RECEIVED.search(accounts.name(c))
    ]
    if dividends:
        put(DIVIDENDS_PAID, _sum(accounts, dividends), dividends[0])
    shares = _shares_in_units(shares, accounts.value(equity_code) if equity_code else None)
    if shares is not None and shares > 0 and out:
        out.append(
            StatementFact(
                cnpj=doc.cnpj,
                doc_type=doc.doc_type,
                reference_date=doc.reference_date,
                version=doc.version,
                delivered_on=doc.delivered_on,
                basis=basis,
                template=template,
                metric=SHARES,
                period_start=None,
                period_end=doc.reference_date,
                value=shares,
            )
        )
    return out


# --- point in time --------------------------------------------------------------------------


@dataclass(frozen=True)
class PitFundamentals:
    """What was known about a company on `as_of`: trailing twelve months and the last balance."""

    cnpj: str
    as_of: date
    reference_date: date
    delivered_on: date
    doc_type: str
    version: int
    template: str
    values: Mapping[str, float] = field(default_factory=dict)  # flows: trailing 12 months

    def get(self, metric: str) -> float | None:
        return self.values.get(metric)

    @property
    def net_debt(self) -> float | None:
        if self.template != COMPANY:
            return None
        debt = (self.get(DEBT_CURRENT) or 0.0) + (self.get(DEBT_NONCURRENT) or 0.0)
        cash = (self.get(CASH) or 0.0) + (self.get(SHORT_TERM_INVESTMENTS) or 0.0)
        return debt - cash

    @property
    def ebitda(self) -> float | None:
        ebit = self.get(EBIT)
        if self.template != COMPANY or ebit is None:
            return None
        return ebit + (self.get(DEPRECIATION) or 0.0)

    @property
    def controlling_equity(self) -> float | None:
        equity = self.get(EQUITY)
        return None if equity is None else equity - (self.get(MINORITY_INTEREST) or 0.0)


def _months(start: date, end: date) -> float:
    return (end - start).days / 30.44


def _close(a: date, b: date, days: int = 7) -> bool:
    return abs((a - b).days) <= days


def visible(facts: Sequence[StatementFact], as_of: date) -> list[StatementFact]:
    """The facts delivered by `as_of`, of the newest version delivered of each statement."""
    newest: dict[tuple[str, date], int] = {}
    for f in facts:
        if f.delivered_on <= as_of:
            key = (f.doc_type, f.reference_date)
            newest[key] = max(newest.get(key, 0), f.version)
    return [
        f
        for f in facts
        if f.delivered_on <= as_of and newest.get((f.doc_type, f.reference_date)) == f.version
    ]


def _trailing(flows: Mapping[tuple[date, date], float], start: date, end: date) -> float | None:
    """Twelve months to `end` from a year-to-date value and the last annual statement."""
    value = flows.get((start, end))
    if value is None:
        return None
    if _months(start, end) >= 11.5:
        return value
    year_end = start - timedelta(days=1)
    annual = next(
        (v for (s, e), v in flows.items() if _close(e, year_end, 3) and _months(s, e) >= 11.5),
        None,
    )
    if annual is None:
        return None
    prior_start = next(
        (s for (s, e) in flows if _close(e, year_end, 3) and _months(s, e) >= 11.5), None
    )
    prior = next(
        (
            v
            for (s, e), v in flows.items()
            if prior_start is not None
            and _close(s, prior_start, 3)
            and _close(e, end - timedelta(days=365))
        ),
        None,
    )
    if prior is None:
        return None
    return value + annual - prior


def point_in_time(facts: Sequence[StatementFact], as_of: date) -> PitFundamentals | None:
    """The company's fundamentals as they were known on `as_of` (None before any delivery)."""
    seen = visible(facts, as_of)
    if not seen:
        return None
    last_ref = max(f.reference_date for f in seen)
    latest = [f for f in seen if f.reference_date == last_ref]
    # An annual and a quarterly statement may share the date (rare): the annual one wins.
    doc_type = DFP if any(f.doc_type == DFP for f in latest) else ITR
    latest = [f for f in latest if f.doc_type == doc_type]
    flows: dict[str, dict[tuple[date, date], float]] = defaultdict(dict)
    for f in sorted(seen, key=lambda x: x.delivered_on):
        if f.period_start is not None:
            flows[f.metric][(f.period_start, f.period_end)] = f.value
    values: dict[str, float] = {}
    for f in latest:
        if f.period_start is None:
            values[f.metric] = f.value
        else:
            ttm = _trailing(flows[f.metric], f.period_start, f.period_end)
            if ttm is not None:
                values[f.metric] = ttm
    head = latest[0]
    return PitFundamentals(
        cnpj=head.cnpj,
        as_of=as_of,
        reference_date=last_ref,
        delivered_on=max(f.delivered_on for f in latest),
        doc_type=doc_type,
        version=head.version,
        template=head.template,
        values=values,
    )


def delivery_history(facts: Sequence[StatementFact]) -> list[PitFundamentals]:
    """What was known right after each delivery, newest first (one row per delivery day)."""
    days = sorted({f.delivered_on for f in facts}, reverse=True)
    out = []
    for day in days:
        pit = point_in_time(facts, day)
        if pit is not None and pit.delivered_on == day:
            out.append(pit)
    return out
