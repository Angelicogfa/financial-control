"""B3 Área do Investidor statements: trades (Negociação) and movements (Movimentação), 12.3.

The parser is pure: it receives the spreadsheet rows as dictionaries (header -> cell) and
returns normalized lines. Every line carries a content hash; importing the same file twice
creates nothing new. Identical rows of one file are told apart by their occurrence index.

Movements map to:
- Dividendo / Juros Sobre Capital Próprio / Rendimento -> earnings (JCP grossed up from the
  net value B3 shows, with 15% withheld);
- Desdobro / Bonificação em Ativos -> SPLIT / BONUS (shares credited are added to the
  quantity held the day before); Grupamento -> REVERSE_SPLIT (the line shows the new total);
- Transferência - Liquidação -> ignored, the trade itself comes from the Negociação file;
- Tesouro Direto Compra/Venda and bank securities (CDB, LCI, LCA, CRI, CRA) Aplicação/Resgate
  -> trades, since they never reach the Negociação file. B3 gives them no ticker:
  `resolve_fixed_income` points them at the registered Treasury bond, or at the one asset
  of that kind and issuer (all applications of one bank share an asset);
- anything else -> ignored with the reason.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from domain.shared.entities import AssetEntity
from domain.shared.enums import (
    AssetType,
    CorporateEventKind,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)

JCP_WITHHOLDING = Decimal("0.15")
# The issuer code may carry digits (B3SA3F), so only the trailing class number is fixed.
FRACTIONAL_SUFFIX = re.compile(r"^([A-Z0-9]{4}\d{1,2})F$")
TICKER = re.compile(r"^([A-Z0-9]{4,6}\d{0,2})\b")


class StatementKind(StrEnum):
    NEGOTIATION = "NEGOTIATION"
    MOVEMENT = "MOVEMENT"


class LineAction(StrEnum):
    TRADE = "TRADE"
    EARNING = "EARNING"
    EVENT = "EVENT"
    IGNORED = "IGNORED"


class LineStatus(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    UNKNOWN_ASSET = "UNKNOWN_ASSET"
    IGNORED = "IGNORED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class FixedIncomeRef:
    """A Treasury bond or bank-issued security named by a movement line.

    B3 has no ticker for them, so `key` groups the lines meant for one asset: one per
    Treasury bond, and one per instrument kind and issuer for bank securities (every
    application gets its own B3 code, kept in `code`).
    """

    key: str
    name: str
    asset_type: AssetType
    instrument_kind: FixedIncomeInstrumentKind
    indexer: FixedIncomeIndexer
    issuer: str
    maturity_year: int | None = None
    semiannual: bool = False
    code: str | None = None


@dataclass(frozen=True)
class ImportLine:
    line_no: int
    source: StatementKind
    action: LineAction
    when: date | None
    ticker: str | None
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    trade_kind: TransactionKind | None = None
    earning_kind: EarningKind | None = None
    gross_amount: Decimal | None = None
    withholding_tax: Decimal | None = None
    event_kind: CorporateEventKind | None = None
    institution: str | None = None
    fixed_income: FixedIncomeRef | None = None
    hash: str = ""
    status: LineStatus = LineStatus.NEW
    note: str = ""


@dataclass(frozen=True)
class ImportPreview:
    kind: StatementKind
    lines: list[ImportLine]

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(line.status.value for line in self.lines))

    @property
    def unknown_tickers(self) -> list[str]:
        return sorted(
            {
                line.ticker
                for line in self.lines
                if line.status == LineStatus.UNKNOWN_ASSET and line.ticker
            }
        )

    @property
    def new_lines(self) -> list[ImportLine]:
        return [line for line in self.lines if line.status == LineStatus.NEW]


def _norm(text: object) -> str:
    raw = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(raw.lower().split())


NEGOTIATION_HEADERS = {"data do negocio", "tipo de movimentacao", "codigo de negociacao"}
MOVEMENT_HEADERS = {"entrada/saida", "movimentacao", "produto"}


def detect_kind(headers: Iterable[object]) -> StatementKind:
    names = {_norm(h) for h in headers}
    if names >= NEGOTIATION_HEADERS:
        return StatementKind.NEGOTIATION
    if names >= MOVEMENT_HEADERS:
        return StatementKind.MOVEMENT
    raise ValueError("Not a B3 Negociação or Movimentação statement")


def _cell(row: Mapping[str, object], name: str) -> object:
    for key, value in row.items():
        if _norm(key) == name:
            return value
    return None


def _date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if text in ("", "-"):
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _ticker(code: object) -> str | None:
    text = str(code or "").strip().upper()
    if not text:
        return None
    match = TICKER.match(text.split(" - ")[0].strip())
    if not match:
        return None
    ticker = match.group(1)
    fractional = FRACTIONAL_SUFFIX.match(ticker)
    return fractional.group(1) if fractional else ticker


def _hash(parts: Iterable[object]) -> str:
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _with_hashes(lines: list[ImportLine]) -> list[ImportLine]:
    seen: Counter[str] = Counter()
    hashed = []
    for line in lines:
        key = _hash(
            (
                "b3",
                line.source.value,
                line.when,
                line.ticker,
                line.description,
                line.quantity,
                line.unit_price,
                line.amount,
            )
        )
        seen[key] += 1
        hashed.append(replace(line, hash=_hash((key, seen[key]))))
    return hashed


def _negotiation_line(n: int, row: Mapping[str, object]) -> ImportLine:
    side = _norm(_cell(row, "tipo de movimentacao"))
    when = _date(_cell(row, "data do negocio"))
    ticker = _ticker(_cell(row, "codigo de negociacao"))
    qty = _decimal(_cell(row, "quantidade"))
    price = _decimal(_cell(row, "preco"))
    amount = _decimal(_cell(row, "valor"))
    base = ImportLine(
        n,
        StatementKind.NEGOTIATION,
        LineAction.TRADE,
        when,
        ticker,
        side or "-",
        quantity=qty,
        unit_price=price,
        amount=amount,
        institution=str(_cell(row, "instituicao") or "") or None,
    )
    kind = {"compra": TransactionKind.BUY, "venda": TransactionKind.SELL}.get(side)
    if kind is None or when is None or not ticker or not qty or qty <= 0 or price is None:
        return replace(base, status=LineStatus.INVALID, note="Linha incompleta ou desconhecida")
    return replace(base, trade_kind=kind)


EARNINGS = {
    "dividendo": EarningKind.DIVIDEND,
    "juros sobre capital proprio": EarningKind.JCP,
    "rendimento": EarningKind.FII_YIELD,
}
EVENTS = {
    "desdobro": CorporateEventKind.SPLIT,
    "bonificacao em ativos": CorporateEventKind.BONUS,
    "grupamento": CorporateEventKind.REVERSE_SPLIT,
}


TREASURY_PRODUCT = re.compile(r"^(tesouro .+?) (\d{4})$")
BANK_PRODUCT = re.compile(r"^(CDB|LCI|LCA|CRI|CRA)\s*-\s*([A-Z0-9]+)(?:\s*-\s*(.+))?$")
TREASURY_ISSUER = "Tesouro Nacional"
TREASURY_KINDS = (
    ("selic", FixedIncomeInstrumentKind.TESOURO_SELIC, FixedIncomeIndexer.SELIC),
    ("prefixado", FixedIncomeInstrumentKind.TESOURO_PRE, FixedIncomeIndexer.PRE),
    ("ipca", FixedIncomeInstrumentKind.TESOURO_IPCA, FixedIncomeIndexer.IPCA),
    ("renda+", FixedIncomeInstrumentKind.TESOURO_IPCA, FixedIncomeIndexer.IPCA),
    ("educa+", FixedIncomeInstrumentKind.TESOURO_IPCA, FixedIncomeIndexer.IPCA),
)
# Movement -> trade side, per family. Tesouro Direto shows Compra/Venda; bank securities
# show Aplicação and Resgate (early or at maturity).
FIXED_INCOME_TRADES = {
    AssetType.TREASURY: {
        "compra": TransactionKind.BUY,
        "venda": TransactionKind.SELL,
        "vencimento": TransactionKind.SELL,
    },
    AssetType.FIXED_INCOME: {
        "aplicacao": TransactionKind.BUY,
        "resgate antecipado": TransactionKind.SELL,
        "resgate": TransactionKind.SELL,
        "vencimento": TransactionKind.SELL,
    },
}
FIXED_INCOME_COUPONS = {"juros", "rendimento", "amortizacao"}


def _code_slug(text: str, limit: int) -> str:
    return re.sub(r"[^A-Z0-9]", "", _norm(text).upper())[:limit] or "X"


def _fixed_income_ref(product: object, institution: object) -> FixedIncomeRef | None:
    """The Treasury bond or bank security a movement names, or None for exchange codes."""
    raw = " ".join(str(product or "").split())
    treasury = TREASURY_PRODUCT.match(_norm(raw))
    if treasury:
        title, year = treasury.groups()
        kind, indexer = next(
            ((k, i) for word, k, i in TREASURY_KINDS if word in title),
            (None, None),
        )
        if kind is None or indexer is None:
            return None
        semiannual = "juros semestrais" in title
        key = f"{kind.value}{'-JS' if semiannual else ''}-{year}"
        return FixedIncomeRef(
            key=key,
            name=raw,
            asset_type=AssetType.TREASURY,
            instrument_kind=kind,
            indexer=indexer,
            issuer=TREASURY_ISSUER,
            maturity_year=int(year),
            semiannual=semiannual,
        )
    bank = BANK_PRODUCT.match(raw.upper())
    if bank:
        kind_name, code, product_issuer = bank.groups()
        issuer = " ".join(str(product_issuer or institution or "").split()) or kind_name
        return FixedIncomeRef(
            key=f"{kind_name}-{_code_slug(issuer, 12)}",
            name=f"{kind_name} {issuer}",
            asset_type=AssetType.FIXED_INCOME,
            instrument_kind=FixedIncomeInstrumentKind(kind_name),
            indexer=FixedIncomeIndexer.CDI,
            issuer=issuer,
            code=code,
        )
    return None


def _fixed_income_line(base: ImportLine, movement: str, ref: FixedIncomeRef) -> ImportLine:
    # Before matching an asset, the line is keyed by the bond, or by the B3 code of the
    # bank security, so its hash never depends on how the user registered the asset.
    base = replace(base, ticker=ref.code or ref.key, fixed_income=ref)
    if base.when is None:
        return replace(base, note="Sem data")
    side = FIXED_INCOME_TRADES[ref.asset_type].get(movement)
    if side is not None:
        if not base.quantity or base.quantity <= 0 or not base.unit_price:
            return replace(base, status=LineStatus.INVALID, note="Linha sem quantidade ou preço")
        return replace(base, action=LineAction.TRADE, status=LineStatus.NEW, trade_kind=side)
    if ref.asset_type == AssetType.TREASURY and movement in FIXED_INCOME_COUPONS:
        if not base.amount or base.amount <= 0:
            return replace(base, status=LineStatus.INVALID, note="Provento sem valor")
        return replace(
            base,
            action=LineAction.EARNING,
            status=LineStatus.NEW,
            earning_kind=EarningKind.FIXED_INCOME_COUPON,
            gross_amount=base.amount,
            withholding_tax=Decimal("0"),
        )
    return replace(base, note="Movimentação não suportada")


def _movement_line(n: int, row: Mapping[str, object]) -> ImportLine:
    movement = _norm(_cell(row, "movimentacao"))
    when = _date(_cell(row, "data"))
    ticker = _ticker(_cell(row, "produto"))
    qty = _decimal(_cell(row, "quantidade"))
    price = _decimal(_cell(row, "preco unitario"))
    amount = _decimal(_cell(row, "valor da operacao"))
    base = ImportLine(
        n,
        StatementKind.MOVEMENT,
        LineAction.IGNORED,
        when,
        ticker,
        movement or "-",
        quantity=qty,
        unit_price=price,
        amount=amount,
        institution=str(_cell(row, "instituicao") or "") or None,
        status=LineStatus.IGNORED,
    )
    ref = _fixed_income_ref(_cell(row, "produto"), base.institution)
    if ref is not None:
        return _fixed_income_line(base, movement, ref)
    if when is None or not ticker:
        return replace(base, note="Sem data ou ativo")
    if movement in EARNINGS:
        if not amount or amount <= 0:
            return replace(base, status=LineStatus.INVALID, note="Provento sem valor")
        kind = EARNINGS[movement]
        gross, tax = amount, Decimal("0")
        if kind == EarningKind.JCP:
            gross = (amount / (1 - JCP_WITHHOLDING)).quantize(Decimal("0.01"))
            tax = gross - amount
        return replace(
            base,
            action=LineAction.EARNING,
            status=LineStatus.NEW,
            earning_kind=kind,
            gross_amount=gross,
            withholding_tax=tax,
        )
    if movement in EVENTS:
        if not qty or qty <= 0:
            return replace(base, status=LineStatus.INVALID, note="Evento sem quantidade")
        return replace(
            base, action=LineAction.EVENT, status=LineStatus.NEW, event_kind=EVENTS[movement]
        )
    if movement.startswith("transferencia - liquidacao"):
        return replace(base, note="Liquidação de negócio: importe a planilha de Negociação")
    return replace(base, note="Movimentação não suportada")


def parse_statement(rows: list[Mapping[str, object]]) -> ImportPreview:
    """Normalize the rows of a B3 statement (first row of the sheet are the headers)."""
    if not rows:
        raise ValueError("Empty statement")
    kind = detect_kind(rows[0].keys())
    build = _negotiation_line if kind == StatementKind.NEGOTIATION else _movement_line
    lines = [
        build(n, row)
        for n, row in enumerate(rows, start=2)
        if any(v not in (None, "") for v in row.values())
    ]
    return ImportPreview(kind, _with_hashes(lines))


SKIPPED_NOTE = "Ignorada por você"


def mark_skipped(preview: ImportPreview, line_nos: Iterable[int]) -> ImportPreview:
    """Leave out the lines the user chose not to import; already imported ones stay as they are."""
    skipped = set(line_nos)
    if not skipped:
        return preview
    return ImportPreview(
        preview.kind,
        [
            replace(line, status=LineStatus.IGNORED, note=SKIPPED_NOTE)
            if line.line_no in skipped and line.status != LineStatus.DUPLICATE
            else line
            for line in preview.lines
        ],
    )


def _issuer_slug(text: str | None) -> str:
    # "ITAU UNIBANCO S.A." and "Itaú Unibanco" name the same issuer.
    return re.sub(r"[^a-z0-9]", "", _norm(text)).removesuffix("sa")


def _matches_fixed_income(ref: FixedIncomeRef, asset: AssetEntity) -> bool:
    term = asset.fixed_income_term
    if asset.asset_type != ref.asset_type:
        return False
    if ref.asset_type == AssetType.TREASURY:
        if _norm(asset.name) == _norm(ref.name):
            return True
        return (
            term is not None
            and term.instrument_kind == ref.instrument_kind
            and term.maturity_date is not None
            and term.maturity_date.year == ref.maturity_year
            and ("juros semestrais" in _norm(asset.name)) == ref.semiannual
        )
    if term is None or term.instrument_kind != ref.instrument_kind:
        return False
    wanted, held = _issuer_slug(ref.issuer), _issuer_slug(term.issuer)
    return bool(wanted and held) and (wanted.startswith(held) or held.startswith(wanted))


def resolve_fixed_income(
    preview: ImportPreview,
    assets: Iterable[AssetEntity],
    *,
    chosen: Mapping[str, str] | None = None,
) -> ImportPreview:
    """Point each Treasury/bank line at its registered asset.

    An asset whose ticker is the B3 code of the security wins; otherwise the Treasury bond
    (same name, or kind and maturity year) or the asset of the same kind and issuer. Lines
    with no asset take the group key, which `classify` reports as an unknown asset;
    `chosen` maps a group key to the asset just registered for it.
    """
    candidates = [a for a in assets if a.asset_type in FIXED_INCOME_TRADES]
    by_ticker = {a.ticker: a for a in candidates}
    resolved = []
    for line in preview.lines:
        ref = line.fixed_income
        if ref is None:
            resolved.append(line)
            continue
        if chosen and ref.key in chosen:
            resolved.append(replace(line, ticker=chosen[ref.key]))
            continue
        if ref.code and ref.code in by_ticker:
            resolved.append(replace(line, ticker=ref.code))
            continue
        matches = sorted(a.ticker for a in candidates if _matches_fixed_income(ref, a))
        if len(matches) == 1:
            resolved.append(replace(line, ticker=matches[0]))
        elif matches and line.status == LineStatus.NEW:
            resolved.append(
                replace(
                    line,
                    status=LineStatus.INVALID,
                    note=f"Mais de um ativo combina: {', '.join(matches)}",
                )
            )
        else:
            resolved.append(replace(line, ticker=ref.key))
    return ImportPreview(preview.kind, resolved)


def event_factor(
    kind: CorporateEventKind, line_quantity: Decimal, held_before: Decimal
) -> Decimal | None:
    """Quantity factor of an event line given the shares held right before it."""
    if held_before <= 0:
        return None
    if kind == CorporateEventKind.REVERSE_SPLIT:
        factor = line_quantity / held_before
        return factor if 0 < factor < 1 else None
    return 1 + line_quantity / held_before


def classify(
    preview: ImportPreview,
    *,
    known_tickers: set[str],
    existing_hashes: set[str],
    held_before: Callable[[str, date], Decimal] | None = None,
) -> ImportPreview:
    """Mark each actionable line NEW, DUPLICATE, UNKNOWN_ASSET or INVALID."""
    classified = []
    for line in preview.lines:
        if line.status in (LineStatus.IGNORED, LineStatus.INVALID):
            classified.append(line)
            continue
        if line.hash in existing_hashes:
            classified.append(replace(line, status=LineStatus.DUPLICATE, note="Já importado"))
            continue
        if line.ticker not in known_tickers:
            classified.append(
                replace(line, status=LineStatus.UNKNOWN_ASSET, note="Ativo não cadastrado")
            )
            continue
        if (
            line.action == LineAction.EVENT
            and held_before is not None
            and line.when is not None
            and line.event_kind is not None
            and event_factor(
                line.event_kind, line.quantity or Decimal("0"), held_before(line.ticker, line.when)
            )
            is None
        ):
            classified.append(
                replace(line, status=LineStatus.INVALID, note="Sem posição para aplicar o evento")
            )
            continue
        classified.append(replace(line, status=LineStatus.NEW, note=""))
    return ImportPreview(preview.kind, classified)


def guess_asset_type(ticker: str) -> AssetType | None:
    """B3 code convention: 3-8 shares, 11 units/funds (assumed FII), 32-35 and 39 BDRs."""
    match = re.match(r"^[A-Z]{4}(\d{1,2})$", ticker.strip().upper())
    if not match:
        return None
    suffix = int(match.group(1))
    if suffix in (3, 4, 5, 6, 7, 8):
        return AssetType.STOCK_BR
    if suffix == 11:
        return AssetType.FII
    if suffix in (32, 33, 34, 35, 39):
        return AssetType.BDR
    return None
