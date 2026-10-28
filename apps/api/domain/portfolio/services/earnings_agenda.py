"""Agenda of declared distributions for the portfolio and the watchlist (item 26.3).

An item is upcoming while its payment has not happened: before the data com (`UPCOMING`, you
still get it by holding the share at the close of that day) or between the data com and the
payment (`AWAITING_PAYMENT`, the right is already fixed). The ex date is the business day
after the data com. Held assets get the quantity owned at the data com (today's quantity when
it is still ahead) and the estimated gross and net amounts: JCP withholding from the tax
registry and, from 2026, 10% on dividends above R$ 50 mil per company and month.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from core.helpers.calendar import add_business_days
from domain.market.entities import AnnouncedEarning, AnnouncedStockEvent
from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.shared.entities import AssetEntity
from domain.shared.enums import CorporateEventKind, EarningKind
from domain.tax.entities import TaxRegime, TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK

DIVIDEND_MONTHLY_EXEMPTION_BRL = 50_000.0
DEFAULT_HORIZON_DAYS = 180


class AgendaStatus(StrEnum):
    UPCOMING = "UPCOMING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"


@dataclass(frozen=True)
class AgendaItem:
    ticker: str
    name: str
    asset_id: int | None
    kind: EarningKind
    label: str
    rate: float
    com_date: date | None
    ex_date: date | None
    payment_date: date | None
    status: AgendaStatus
    held: bool
    quantity: float = 0.0
    gross_amount: float | None = None
    withholding_tax: float | None = None
    net_amount: float | None = None
    related_to: str | None = None


@dataclass(frozen=True)
class EarningsAgenda:
    as_of_date: date
    items: list[AgendaItem] = field(default_factory=list)
    declared_net_brl: float = 0.0
    declared_by_month: dict[str, float] = field(default_factory=dict)
    covered_tickers: list[str] = field(default_factory=list)


def earning_kind(label: str) -> EarningKind:
    """Map a B3 distribution label to the ledger kind."""
    upper = label.upper()
    if "JRS" in upper or "JUROS" in upper or "JCP" in upper:
        return EarningKind.JCP
    if "RENDIMENTO" in upper:
        return EarningKind.FII_YIELD
    return EarningKind.DIVIDEND


def stock_event_kind(label: str) -> CorporateEventKind | None:
    upper = label.upper()
    if "DESDOBRAMENTO" in upper:
        return CorporateEventKind.SPLIT
    if "GRUPAMENTO" in upper:
        return CorporateEventKind.REVERSE_SPLIT
    if "BONIFICA" in upper:
        return CorporateEventKind.BONUS
    return None


def ex_date_of(com_date: date | None) -> date | None:
    """The ex date is the first business day after the data com."""
    return add_business_days(com_date, 1) if com_date else None


def quantity_on(asset: AssetEntity, day: date) -> float:
    """Shares held at the close of `day` (zero for an inconsistent ledger)."""
    try:
        return float(
            build_position(
                asset.transactions, up_to_date=day, events=asset.corporate_events
            ).quantity
        )
    except InsufficientQuantityError:
        return 0.0


def _withholding(
    kind: EarningKind, gross: float, payment: date | None, rules: TaxRuleBook, as_of: date
) -> float:
    on = payment or as_of
    if kind == EarningKind.JCP:
        return gross * rules.rule(TaxRegime.JCP_WITHHOLDING, on).brackets[0].rate
    if kind == EarningKind.DIVIDEND:
        rate = rules.rule(TaxRegime.DIVIDEND_WITHHOLDING, on).brackets[0].rate
        return max(0.0, gross - DIVIDEND_MONTHLY_EXEMPTION_BRL) * rate
    return 0.0


def build_agenda(
    assets: Sequence[AssetEntity],
    announcements: Mapping[str, Sequence[AnnouncedEarning]],
    *,
    as_of: date,
    rules: TaxRuleBook | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> EarningsAgenda:
    """Upcoming declared distributions of `assets`, earliest payment first."""
    book = rules or DEFAULT_RULE_BOOK
    horizon = as_of + timedelta(days=horizon_days)
    items: list[AgendaItem] = []
    for asset in assets:
        for announced in announcements.get(asset.ticker, ()):
            payment = announced.payment_date
            com = announced.com_date
            if payment is not None and payment < as_of:
                continue
            if payment is None and (com is None or com < as_of):
                continue
            if (payment or com or as_of) > horizon:
                continue
            status = (
                AgendaStatus.UPCOMING
                if com is None or com >= as_of
                else AgendaStatus.AWAITING_PAYMENT
            )
            quantity = quantity_on(asset, min(com, as_of) if com else as_of)
            kind = earning_kind(announced.label)
            held = quantity > 0
            gross = round(quantity * announced.rate, 2) if held else None
            tax = round(_withholding(kind, gross, payment, book, as_of), 2) if gross else None
            items.append(
                AgendaItem(
                    ticker=asset.ticker,
                    name=asset.name,
                    asset_id=asset.id,
                    kind=kind,
                    label=announced.label,
                    rate=announced.rate,
                    com_date=com,
                    ex_date=ex_date_of(com),
                    payment_date=payment,
                    status=status,
                    held=held,
                    quantity=quantity,
                    gross_amount=gross,
                    withholding_tax=tax,
                    net_amount=round(gross - (tax or 0.0), 2) if gross is not None else None,
                    related_to=announced.related_to,
                )
            )
    items.sort(key=lambda i: (i.payment_date or i.com_date or date.max, i.ticker))
    by_month: dict[str, float] = {}
    for item in items:
        if item.net_amount and item.payment_date:
            key = f"{item.payment_date.year:04d}-{item.payment_date.month:02d}"
            by_month[key] = round(by_month.get(key, 0.0) + item.net_amount, 2)
    return EarningsAgenda(
        as_of_date=as_of,
        items=items,
        declared_net_brl=round(sum(i.net_amount or 0.0 for i in items), 2),
        declared_by_month=dict(sorted(by_month.items())),
        covered_tickers=sorted(announcements),
    )


def resolve_ex_date(
    kind: CorporateEventKind,
    credit_date: date,
    events: Sequence[AnnouncedStockEvent],
    *,
    window_days: int = 45,
) -> date | None:
    """Real ex date of an imported corporate event (TD-08).

    The B3 statement dates splits and bonus issues by the credit of the new shares, days after
    the ex date. The declared event of the same kind whose data com falls within `window_days`
    before the credit gives the ex date (business day after the data com).
    """
    candidates = [
        e.com_date
        for e in events
        if e.com_date is not None
        and stock_event_kind(e.label) == kind
        and credit_date - timedelta(days=window_days) <= e.com_date < credit_date
    ]
    return ex_date_of(max(candidates)) if candidates else None


def resolve_earning_ex_date(
    kind: EarningKind, payment_date: date, earnings: Sequence[AnnouncedEarning]
) -> date | None:
    """Ex date of an imported earning: the declared one of the same kind paid on that day."""
    for announced in earnings:
        if announced.payment_date == payment_date and earning_kind(announced.label) == kind:
            return ex_date_of(announced.com_date)
    return None
