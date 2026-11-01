"""Analytic Hierarchy Process for the lens weights (Phase 45.3, design N5; decision 10.7).

The weights of the eight lenses come from pairwise comparisons on Saaty's 1-9 scale ("quality is
moderately more important than momentum" = 3), one matrix per objective, kept in the versioned
policy. The weights are the principal eigenvector of the matrix; the consistency ratio
CR = ((lambda_max - n) / (n - 1)) / RI(n) says whether the judgements contradict each other
(above 0.10 the policy is refused and the most contradictory pairs are named).

The pre-configured matrices follow the logic of each objective (design N5). They are built from
an intensity per lens: each cell is the ratio of the two intensities rounded to Saaty's scale,
which keeps them nearly consistent (CR from 0.003 to 0.011).

The Gaussian AHP (weights proportional to the coefficient of variation of each lens across the
assets) is only a reference: it rewards the lens that most separates the assets, not the one
that best predicts the return.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.errors import ValidationError
from domain.recommendation.keys import DIVIDENDS, GROWTH, LENS_LABELS, LENSES, MIXED

Matrix = tuple[tuple[float, ...], ...]

MAX_CONSISTENCY_RATIO = 0.10
SAATY_MIN, SAATY_MAX = 1.0 / 9.0, 9.0
# Saaty's random index by matrix size.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}

# Intensity of each lens per objective, in the order of LENSES:
# Cerrado, Quality, Valuation, Improvement, Momentum, Income, Risk, Projection.
_INTENSITIES = {
    GROWTH: (5, 7, 7, 5, 3, 1, 4, 3),
    DIVIDENDS: (5, 6, 5, 2, 1, 9, 5, 2),
    MIXED: (5, 8, 6, 3, 2, 5, 4, 2),
}


def _saaty(ratio: float) -> float:
    if ratio >= 1.0:
        return float(min(9, max(1, round(ratio))))
    return 1.0 / min(9, max(1, round(1.0 / ratio)))


def matrix_from_intensities(intensities: Sequence[float]) -> Matrix:
    n = len(intensities)
    rows = [[1.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            rows[i][j] = _saaty(intensities[i] / intensities[j])
            rows[j][i] = 1.0 / rows[i][j]
    return tuple(tuple(round(v, 6) for v in row) for row in rows)


DEFAULT_MATRICES: dict[str, Matrix] = {
    objective: matrix_from_intensities(values) for objective, values in _INTENSITIES.items()
}


@dataclass(frozen=True)
class Priority:
    weights: dict[str, float]  # lens -> weight, summing to 1
    lambda_max: float
    consistency_ratio: float


def validate(matrix: Sequence[Sequence[float]], *, labels: Sequence[str] = LENSES) -> Matrix:
    """A square, positive, reciprocal matrix on Saaty's scale (rounded to 6 places)."""
    n = len(labels)
    if len(matrix) != n or any(len(row) != n for row in matrix):
        raise ValidationError(
            f"AHP matrix must be {n}x{n} (one row and one column per lens)",
            code="INVALID_AHP_MATRIX",
        )
    out = tuple(tuple(round(float(v), 6) for v in row) for row in matrix)
    for i in range(n):
        if not np.isclose(out[i][i], 1.0):
            raise ValidationError("AHP matrix diagonal must be 1", code="INVALID_AHP_MATRIX")
        for j in range(n):
            v = out[i][j]
            if not SAATY_MIN - 1e-6 <= v <= SAATY_MAX + 1e-6:
                raise ValidationError(
                    "AHP values must be between 1/9 and 9 (Saaty's scale)",
                    code="INVALID_AHP_MATRIX",
                )
            if not np.isclose(v * out[j][i], 1.0, atol=1e-3):
                raise ValidationError(
                    f"AHP matrix must be reciprocal: {LENS_LABELS.get(labels[i], labels[i])} x "
                    f"{LENS_LABELS.get(labels[j], labels[j])} and its inverse do not match",
                    code="INVALID_AHP_MATRIX",
                )
    return out


def priority(matrix: Sequence[Sequence[float]], *, labels: Sequence[str] = LENSES) -> Priority:
    """Weights (principal eigenvector), lambda_max and the consistency ratio."""
    a = np.asarray(matrix, dtype=float)
    n = a.shape[0]
    values, vectors = np.linalg.eig(a)
    k = int(np.argmax(values.real))
    w = np.abs(vectors[:, k].real)
    w = w / w.sum()
    lam = float(values[k].real)
    ci = (lam - n) / (n - 1) if n > 2 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri > 0 else 0.0
    return Priority(
        weights={label: round(float(w[i]), 6) for i, label in enumerate(labels)},
        lambda_max=round(lam, 6),
        consistency_ratio=round(max(cr, 0.0), 6),
    )


def worst_pairs(
    matrix: Sequence[Sequence[float]], *, labels: Sequence[str] = LENSES, count: int = 3
) -> list[tuple[str, str]]:
    """The pairs whose judgement departs most from what the weights imply."""
    found = priority(matrix, labels=labels)
    w = [found.weights[label] for label in labels]
    errors = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            implied = w[i] / w[j]
            errors.append((abs(np.log(matrix[i][j] / implied)), labels[i], labels[j]))
    return [(a, b) for _e, a, b in sorted(errors, reverse=True)[:count]]


def check_consistency(matrix: Sequence[Sequence[float]], *, labels: Sequence[str] = LENSES) -> None:
    """Refuse a matrix whose judgements contradict each other (CR above 0.10)."""
    found = priority(matrix, labels=labels)
    if found.consistency_ratio > MAX_CONSISTENCY_RATIO:
        pairs = "; ".join(
            f"{LENS_LABELS.get(a, a)} x {LENS_LABELS.get(b, b)}"
            for a, b in worst_pairs(matrix, labels=labels)
        )
        raise ValidationError(
            f"AHP judgements are inconsistent (CR {found.consistency_ratio:.3f} > "
            f"{MAX_CONSISTENCY_RATIO}); review: {pairs}",
            code="INCONSISTENT_AHP_MATRIX",
        )


def gaussian_weights(columns: Mapping[str, Sequence[float]]) -> dict[str, float]:
    """Gaussian AHP: weights proportional to each lens's coefficient of variation (reference)."""
    cv = {}
    for lens, values in columns.items():
        arr = np.asarray(values, dtype=float)
        mean = float(arr.mean()) if arr.size else 0.0
        cv[lens] = float(arr.std(ddof=0)) / mean if arr.size > 1 and mean > 0 else 0.0
    total = sum(cv.values())
    if total <= 0:
        return dict.fromkeys(columns, 0.0)
    return {lens: round(v / total, 6) for lens, v in cv.items()}
