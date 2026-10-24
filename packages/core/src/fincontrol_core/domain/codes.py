"""Generated identifiers for assets that have no exchange ticker (item 10.5, finding D-01).

Fixed income and cash positions are identified by instrument kind, issuer and maturity, so
two CDBs never need invented tickers: CDB-BANCOINTER-20270115, LCI-CAIXA-LIQ-2, ...
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from fincontrol_core.domain.entities import FixedIncomeTermEntity
from fincontrol_core.domain.enums import AssetType

MAX_CODE_LENGTH = 32
CODE_ASSET_TYPES = frozenset({AssetType.FIXED_INCOME, AssetType.TREASURY, AssetType.CASH})


def _slug(text: str, limit: int) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", ascii_text.upper())[:limit] or "X"


def generated_asset_code(
    asset_type: AssetType,
    name: str,
    term: FixedIncomeTermEntity | None,
    is_taken: Callable[[str], bool],
) -> str:
    """Readable unique code; `is_taken` reports codes already in use."""
    if term is not None:
        maturity = term.maturity_date.strftime("%Y%m%d") if term.maturity_date else "LIQ"
        base = f"{term.instrument_kind.value}-{_slug(term.issuer or name, 10)}-{maturity}"
    else:
        prefix = "CAIXA" if asset_type == AssetType.CASH else asset_type.value
        base = f"{prefix}-{_slug(name, 16)}"
    base = base[: MAX_CODE_LENGTH - 4]
    candidate, counter = base, 1
    while is_taken(candidate):
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate
