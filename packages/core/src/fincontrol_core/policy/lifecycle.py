"""Asset lifecycle under the investment policy (item 10.6, ADR 0005).

WATCHLIST -> ELIGIBLE -> HELD -> REVIEW -> ARCHIVED

- ARCHIVED: the asset was deactivated.
- HELD / REVIEW: there is an open position; REVIEW when it no longer meets the policy.
- ELIGIBLE / WATCHLIST: no position; ELIGIBLE when it meets the policy.

Only ELIGIBLE and HELD assets receive contributions. REVIEW raises attention but never
triggers an automatic sale.
"""

from __future__ import annotations

from collections.abc import Iterable

from fincontrol_core.cerrado.scoring import CerradoEvaluation
from fincontrol_core.domain.entities import AssetEntity, CorporateEventEntity, TransactionEntity
from fincontrol_core.domain.enums import AssetLifecycle, AssetPurpose, TransactionKind
from fincontrol_core.policy.models import EligibilityPolicy

CONTRIBUTION_STATUSES = frozenset({AssetLifecycle.ELIGIBLE, AssetLifecycle.HELD})


def is_eligible(
    evaluation: CerradoEvaluation,
    policy: EligibilityPolicy,
    purpose: AssetPurpose = AssetPurpose.ARCA,
) -> bool:
    """Whether an asset meets the fundamentalist criteria of the policy."""
    if purpose != AssetPurpose.ARCA or not evaluation.use_cerrado:
        return True
    if evaluation.answered == 0:
        return not policy.require_evaluation
    coverage_pct = evaluation.answered / evaluation.max_score * 100.0 if evaluation.max_score else 0
    return evaluation.score >= policy.min_score and coverage_pct >= policy.min_coverage_pct


def has_position(
    transactions: Iterable[TransactionEntity],
    *,
    fixed_income: bool,
    events: Iterable[CorporateEventEntity] = (),
) -> bool:
    """Open position from the ledger: units for market assets, money for fixed income."""
    entries = list(transactions)
    if fixed_income:
        bought = sum(float(t.quantity * t.unit_price) for t in entries if t.kind == "BUY")
        sold = sum(float(t.quantity * t.unit_price) for t in entries if t.kind == "SELL")
        return bought > 0 and sold < bought
    # Imported here: the portfolio package imports this module (consolidation).
    from fincontrol_core.portfolio.positions import InsufficientQuantityError, build_position

    try:
        return build_position(entries, events=events).quantity > 0
    except InsufficientQuantityError:
        held = sum(
            float(t.quantity) if t.kind == TransactionKind.BUY else -float(t.quantity)
            for t in entries
        )
        return held > 1e-9


def lifecycle_status(*, is_active: bool, holds_position: bool, eligible: bool) -> AssetLifecycle:
    if not is_active:
        return AssetLifecycle.ARCHIVED
    if holds_position:
        return AssetLifecycle.HELD if eligible else AssetLifecycle.REVIEW
    return AssetLifecycle.ELIGIBLE if eligible else AssetLifecycle.WATCHLIST


def asset_lifecycle(
    asset: AssetEntity, evaluation: CerradoEvaluation, policy: EligibilityPolicy
) -> tuple[AssetLifecycle, bool]:
    """(status, eligible) for an asset given its checklist evaluation."""
    eligible = is_eligible(evaluation, policy, asset.purpose)
    status = lifecycle_status(
        is_active=asset.is_active,
        holds_position=has_position(
            asset.transactions,
            fixed_income=asset.fixed_income_term is not None,
            events=asset.corporate_events,
        ),
        eligible=eligible,
    )
    return status, eligible
