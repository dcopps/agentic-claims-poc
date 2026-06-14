"""
Claims domain — the system-of-record for submitted claims.

Public surface:

  - `ClaimSubmission` / `ClaimRecord` — the request and persisted shapes.
  - `ClaimStatus` / `ClaimType` / `ScenarioTag` — the locked enumerations.
  - `ClaimsRepository` — connection-scoped insert / read / list / status-update.
"""

from backend.app.claims.models import (
    ClaimRecord,
    ClaimStatus,
    ClaimSubmission,
    ClaimType,
    ScenarioTag,
)
from backend.app.claims.repository import ClaimsRepository

__all__ = [
    "ClaimRecord",
    "ClaimStatus",
    "ClaimSubmission",
    "ClaimType",
    "ClaimsRepository",
    "ScenarioTag",
]
