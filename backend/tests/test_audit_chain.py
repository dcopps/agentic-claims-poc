"""
Hash primitive tests — pure functions, no database.

Pin the SHA-256 outputs to known values so a future regression to a
different hash algorithm or a different input encoding fails loudly.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app.audit.chain import (
    GENESIS_CHAIN_HASH,
    HASH_HEX_LENGTH,
    compute_chain_hash,
    compute_row_hash,
)


def test_genesis_constant_is_64_zeros() -> None:
    assert GENESIS_CHAIN_HASH == "0" * 64
    assert len(GENESIS_CHAIN_HASH) == HASH_HEX_LENGTH


def test_compute_row_hash_matches_sha256_of_canonical_bytes() -> None:
    canonical = b'{"agent":"orchestrator","step":"x"}'
    expected = hashlib.sha256(canonical).hexdigest()
    assert compute_row_hash(canonical) == expected
    assert len(compute_row_hash(canonical)) == HASH_HEX_LENGTH


def test_compute_row_hash_rejects_non_bytes() -> None:
    with pytest.raises(TypeError) as excinfo:
        compute_row_hash("not-bytes")  # type: ignore[arg-type]
    assert "expected bytes" in str(excinfo.value)


def test_compute_row_hash_rejects_empty() -> None:
    with pytest.raises(ValueError) as excinfo:
        compute_row_hash(b"")
    assert "refuses empty" in str(excinfo.value)


def test_compute_chain_hash_chains_to_known_value() -> None:
    """Pin the chain formula: sha256( row_hash || prev_chain_hash )."""
    row_hash = "a" * 64
    prev = "b" * 64
    expected = hashlib.sha256((row_hash + prev).encode("utf-8")).hexdigest()
    assert compute_chain_hash(row_hash, prev) == expected


def test_compute_chain_hash_rejects_short_input() -> None:
    with pytest.raises(ValueError) as excinfo:
        compute_chain_hash("short", "b" * 64)
    assert "must be 64 hex chars" in str(excinfo.value)


def test_compute_chain_hash_rejects_non_hex_input() -> None:
    with pytest.raises(ValueError) as excinfo:
        compute_chain_hash("g" * 64, "b" * 64)
    assert "is not valid hex" in str(excinfo.value)


def test_compute_chain_hash_rejects_uppercase_hex() -> None:
    with pytest.raises(ValueError) as excinfo:
        compute_chain_hash("A" * 64, "b" * 64)
    assert "must be lowercase hex" in str(excinfo.value)
