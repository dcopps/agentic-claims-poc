"""
Runs domain — reconstruct past pipeline runs from the audit_log.

Public surface:

  - `RunsRepository` — pure-read reconstruction: `get_run`, `list_runs_for_claim`,
    `list_recent_runs`, `count_runs_by_claim`, `is_run_active`, `compare`.
  - `RunSummary` / `RunListItem` / `RunComparison` / `DiffSummary` — the typed
    run views.
  - `RunNotFoundError` / `RunClaimMismatchError` — comparison guards the API maps
    to 404 / 400.
"""

from backend.app.runs.models import (
    DiffSummary,
    RunComparison,
    RunListItem,
    RunStatus,
    RunSummary,
)
from backend.app.runs.repository import (
    RunClaimMismatchError,
    RunNotFoundError,
    RunsRepository,
    compute_diff,
)

__all__ = [
    "DiffSummary",
    "RunClaimMismatchError",
    "RunComparison",
    "RunListItem",
    "RunNotFoundError",
    "RunStatus",
    "RunSummary",
    "RunsRepository",
    "compute_diff",
]
