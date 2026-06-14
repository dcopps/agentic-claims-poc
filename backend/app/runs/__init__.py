"""
Runs domain — reconstruct past pipeline runs from the audit_log.

Public surface:

  - `RunsRepository` — pure-read reconstruction: `get_run`, `list_runs_for_claim`,
    `is_run_active`, `compare`.
  - `RunSummary` / `RunComparison` / `DiffSummary` — the typed run views.
  - `RunNotFoundError` / `RunClaimMismatchError` — comparison guards the API maps
    to 404 / 400.
"""

from backend.app.runs.models import DiffSummary, RunComparison, RunStatus, RunSummary
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
    "RunNotFoundError",
    "RunStatus",
    "RunSummary",
    "RunsRepository",
    "compute_diff",
]
