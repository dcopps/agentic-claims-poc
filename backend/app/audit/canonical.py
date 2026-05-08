"""
Canonicalisation — produces the deterministic UTF-8 byte string we hash.

The canonical form is the contract between `AuditWriter` and
`verify_chain`. The same logical `AuditEvent` must always produce the
same bytes. If two encodings of equivalent events differ by a single
byte, the verifier will report a ghost break. Changing this function
after Phase 1 invalidates every previously-written row, so it is
treated as a stable interface.

Choices, all deliberate:

  - `sort_keys=True` — JSON object key order is undefined; sorting pins it.
  - `separators=(",", ":")` — strips all whitespace, removing variation
    from prettifiers and from differing default separators.
  - `mode="python"` on Pydantic dump — yields raw Python types so the
    `default` callback below sees `Decimal`, `set`, `bytes` directly and
    can refuse them. (Pydantic's JSON mode silently converts them; that
    silent conversion is exactly what the contract forbids.)
  - `default` handles JSON-safe encoding for known types (UUID,
    datetime) and rejects ambiguous types (`Decimal`, `set`, `bytes`)
    rather than letting Python pick a representation we'd later regret.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.app.audit.event import AuditEvent


def canonicalise(event: AuditEvent) -> bytes:
    """
    Produce the deterministic UTF-8 JSON encoding of `event`.

    Sanitise → validate → abort → execute:
      1. Sanitise: dump the model in Python mode so the encoder sees the
         original types (UUID, datetime, Decimal, set, bytes...).
      2. Validate: `default` accepts known types and refuses ambiguous
         ones. JSON-native scalars (str, int, float, bool, None, dict,
         list) bypass `default` entirely and serialise as expected.
      3. Abort: `default` raises `TypeError` on refusal, which
         `json.dumps` propagates with the value's type in the message.
      4. Execute: serialise with sorted keys and no whitespace, encode
         to UTF-8.
    """
    payload = event.model_dump(mode="python")
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_encode_or_reject,
    ).encode("utf-8")


def _encode_or_reject(value: Any) -> Any:
    """
    Encode known types or refuse ambiguous ones.

    Known: UUID -> string, datetime/date -> ISO 8601 (UTC for datetimes).

    Refused (caller must convert at the call site):

    `Decimal` -> caller must convert to a string explicitly so the
    rounding decision is visible at the call site, not buried in a JSON
    encoder default.

    `set` -> ordering is undefined; if the caller wants a sorted list,
    they must produce one.

    `bytes` -> JSON has no native byte representation; caller must
    base64-encode (or hex-encode) explicitly so the decode path is
    documented.
    """
    # Known JSON-safe encodings — applied here rather than via
    # `mode="json"` so the rejection cases below get to see Decimals,
    # sets, and bytes before Pydantic silently transforms them.
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError(
                "naive datetime in audit payload — convert to UTC at the "
                "call site so the canonical encoding is stable"
            )
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        raise TypeError(
            "Decimal in audit payload — convert to a string at the call site "
            "so the rounding decision is explicit; "
            f"got value={str(value)[:200]!r}"
        )
    if isinstance(value, set | frozenset):
        raise TypeError(
            "set/frozenset in audit payload — ordering is undefined; "
            f"convert to a sorted list at the call site. Got {type(value).__name__}"
        )
    if isinstance(value, bytes | bytearray):
        raise TypeError(
            "bytes in audit payload — encode explicitly (base64 or hex) at "
            "the call site so the decode path is documented. Got "
            f"{type(value).__name__} of length {len(value)}"
        )
    raise TypeError(
        f"audit payload contains unsupported type {type(value).__name__}; "
        "convert to a JSON-safe representation at the call site"
    )
