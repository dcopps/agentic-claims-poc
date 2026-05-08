"""
Tamper-evident audit vault.

The audit log is an append-only, hash-chained ledger. Every row stores
its own SHA-256 row hash plus a chain hash that incorporates the previous
row's chain hash. Any tampering — to a payload, a step, anything — breaks
the row's hash. Tampering with a chain hash itself breaks the next row's
chain hash. The result: a single mutation anywhere produces a deterministic
break a verifier can locate.

Public surface:

  - `AuditEvent` — the typed event a caller hands to the writer.
  - `AuditWriter` — appends an event and returns the persisted row.
  - `verify_chain` — walks the table and reports the first break.

The canonicalisation function (see `canonical.canonicalise`) is the
contract between writer and verifier: the same logical event must always
produce the same bytes, or the verification step would report ghost
breaks. Changing it after Phase 1 invalidates every existing audit row,
so it is treated as a fixed interface.
"""

from backend.app.audit.event import AuditEvent
from backend.app.audit.verify import (
    AuditBreak,
    ChainVerification,
    verify_chain,
)
from backend.app.audit.writer import AuditRow, AuditWriter

__all__ = [
    "AuditBreak",
    "AuditEvent",
    "AuditRow",
    "AuditWriter",
    "ChainVerification",
    "verify_chain",
]
