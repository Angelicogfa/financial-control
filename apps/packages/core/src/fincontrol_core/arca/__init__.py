"""ARCA macro-allocation module."""

from fincontrol_core.arca.allocation import (
    ArcaTargets,
    ClassAllocation,
    InvalidTargetsError,
    compute_allocation,
    distribute_by_targets,
)

__all__ = [
    "ArcaTargets",
    "ClassAllocation",
    "InvalidTargetsError",
    "compute_allocation",
    "distribute_by_targets",
]
