"""
SHA-256 chain hash primitives.

Two named constants and two pure functions. Kept separate from the
writer so the formula is testable without a database.
"""

from __future__ import annotations

import hashlib

# Genesis prev_chain_hash for the very first row. Sixty-four zeros — a
# valid 64-character hex string that no SHA-256 output can collide with
# in practice (the probability is 2^-256). Documented here so the
# verifier and the writer agree.
GENESIS_CHAIN_HASH: str = "0" * 64

# Length of a SHA-256 hex digest. Pulled into a named constant so the
# database CHAR(64) column, the validators in this module, and the
# verifier all reference one source of truth.
HASH_HEX_LENGTH: int = 64


def compute_row_hash(canonical: bytes) -> str:
    """
    Hash the canonical bytes of an audit event.

    Defensive checks: the input must be `bytes` (not `str`) so the caller
    cannot accidentally hash an unencoded representation. Empty input is
    rejected — a zero-length canonical row is meaningless and almost
    certainly indicates a bug at the call site.
    """
    if not isinstance(canonical, bytes):
        raise TypeError(
            "compute_row_hash expected bytes (the canonical encoding); "
            f"got {type(canonical).__name__}"
        )
    if len(canonical) == 0:
        raise ValueError("compute_row_hash refuses empty canonical input")
    return hashlib.sha256(canonical).hexdigest()


def compute_chain_hash(row_hash: str, prev_chain_hash: str) -> str:
    """
    Hash `(row_hash || prev_chain_hash)` to produce the new chain hash.

    Both inputs must be 64-char lowercase hex. Concatenation is the
    obvious place to introduce a subtle bug (wrong order, wrong
    separator, wrong encoding), so the inputs are checked rather than
    trusted. The bytes hashed are the UTF-8 encoding of the concatenated
    hex string — documented and testable.
    """
    _require_hex_digest("row_hash", row_hash)
    _require_hex_digest("prev_chain_hash", prev_chain_hash)
    payload = f"{row_hash}{prev_chain_hash}".encode()
    return hashlib.sha256(payload).hexdigest()


def _require_hex_digest(name: str, value: str) -> None:
    """Validate that `value` is a 64-character lowercase hex string."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str; got {type(value).__name__}")
    if len(value) != HASH_HEX_LENGTH:
        raise ValueError(
            f"{name} must be {HASH_HEX_LENGTH} hex chars; "
            f"got length={len(value)}"
        )
    # `int(value, 16)` is the cheapest correctness check: any non-hex
    # character raises ValueError, which we re-raise with the field name.
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} is not valid hex: {value!r}") from exc
    if value != value.lower():
        raise ValueError(f"{name} must be lowercase hex; got {value!r}")
