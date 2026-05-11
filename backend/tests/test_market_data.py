"""
Tests for `backend.data.market_data`.

Strategy: every test constructs an isolated YAML file under
`tmp_path` so the module-level loader cache cannot leak between
tests. `clear_market_data_cache()` is also called per-test to be
explicit.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest

from backend.data.market_data import (
    MarketDataTable,
    MarketRange,
    clear_market_data_cache,
    load_market_data,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write_yaml(tmp_path: Path, body: str) -> Path:
    """Write a YAML body to a fresh file and return its path."""
    path = tmp_path / "market_data.yaml"
    path.write_text(dedent(body), encoding="utf-8")
    return path


_VALID_BODY = """
    version: 1
    claim_types:
      water_damage:
        severity_bands:
          minor:    {max_amount: 50000}
          moderate: {max_amount: 150000}
          severe:   {max_amount: null}
        ranges:
          minor:    {floor: 5000,   ceiling: 50000}
          moderate: {floor: 50000,  ceiling: 200000}
          severe:   {floor: 200000, ceiling: 800000}
      fire:
        severity_bands:
          minor:    {max_amount: 100000}
          moderate: {max_amount: 500000}
          severe:   {max_amount: null}
        ranges:
          minor:    {floor: 20000,  ceiling: 120000}
          moderate: {floor: 120000, ceiling: 600000}
          severe:   {floor: 500000, ceiling: 1500000}
"""


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Drop the module-level lookup cache before every test."""
    clear_market_data_cache()


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_load_real_market_data_yaml() -> None:
    """The committed `backend/data/market_data.yaml` parses cleanly."""
    table = load_market_data(Path("backend/data/market_data.yaml"))
    assert isinstance(table, MarketDataTable)
    # Six locked claim_types.
    assert table.supported_claim_types() == sorted(
        ["water_damage", "fire", "wind", "theft", "flood", "storm_complex"]
    )


def test_lookup_returns_typed_range_for_each_demo_amount(tmp_path: Path) -> None:
    """The three locked demo amounts land in the documented cells."""
    table = load_market_data(Path("backend/data/market_data.yaml"))

    auto = table.lookup(claim_type="water_damage", reported_amount=Decimal("85000"))
    assert isinstance(auto, MarketRange)
    assert auto.severity == "moderate"
    assert auto.floor == Decimal("50000")
    assert auto.ceiling == Decimal("200000")
    assert auto.contains(Decimal("85000"))

    threshold = table.lookup(claim_type="fire", reported_amount=Decimal("850000"))
    assert threshold.severity == "severe"
    assert threshold.floor == Decimal("500000")
    assert threshold.ceiling == Decimal("1500000")
    assert threshold.contains(Decimal("850000"))

    guardrail = table.lookup(
        claim_type="storm_complex", reported_amount=Decimal("1400000")
    )
    assert guardrail.severity == "severe"
    assert guardrail.floor == Decimal("600000")
    assert guardrail.ceiling == Decimal("1800000")
    assert guardrail.contains(Decimal("1400000"))


def test_severity_band_boundaries_are_inclusive_on_upper(tmp_path: Path) -> None:
    """`reported_amount == max_amount` lands in the same band."""
    path = _write_yaml(tmp_path, _VALID_BODY)
    table = load_market_data(path)
    # 50_000 is the upper bound for `minor` water_damage, inclusive.
    boundary = table.lookup(claim_type="water_damage", reported_amount=Decimal("50000"))
    assert boundary.severity == "minor"
    # 50_001 crosses into `moderate`.
    next_band = table.lookup(
        claim_type="water_damage", reported_amount=Decimal("50001")
    )
    assert next_band.severity == "moderate"


def test_claim_type_lookup_is_case_insensitive(tmp_path: Path) -> None:
    """Mixed-case claim_type input normalises to the canonical key."""
    path = _write_yaml(tmp_path, _VALID_BODY)
    table = load_market_data(path)
    result = table.lookup(
        claim_type="  Water_Damage  ", reported_amount=Decimal("85000")
    )
    assert result.claim_type == "water_damage"


# --------------------------------------------------------------------------- #
# Defensive guards — each maps to one raise inside the loader/lookup.
# --------------------------------------------------------------------------- #


def test_unknown_claim_type_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, _VALID_BODY)
    table = load_market_data(path)
    with pytest.raises(ValueError) as exc_info:
        table.lookup(claim_type="meteor_strike", reported_amount=Decimal("50000"))
    assert "unknown claim_type" in str(exc_info.value)
    assert "meteor_strike" in str(exc_info.value)
    # The error names the supported set so the caller can self-correct.
    assert "water_damage" in str(exc_info.value)


def test_non_positive_amount_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, _VALID_BODY)
    table = load_market_data(path)
    with pytest.raises(ValueError) as exc_info:
        table.lookup(claim_type="water_damage", reported_amount=Decimal("0"))
    assert "reported_amount must be positive" in str(exc_info.value)


def test_empty_claim_type_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, _VALID_BODY)
    table = load_market_data(path)
    with pytest.raises(ValueError) as exc_info:
        table.lookup(claim_type="   ", reported_amount=Decimal("50000"))
    assert "claim_type is empty" in str(exc_info.value)


def test_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_market_data(missing)
    assert "file does not exist" in str(exc_info.value)


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "market_data.yaml"
    path.write_text("version: 1\nclaim_types: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_market_data(path)
    assert "YAML parse error" in str(exc_info.value)


def test_unsupported_schema_version_raises(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        version: 999
        claim_types:
          water_damage:
            severity_bands:
              minor:    {max_amount: 50000}
              moderate: {max_amount: 150000}
              severe:   {max_amount: null}
            ranges:
              minor:    {floor: 5000,   ceiling: 50000}
              moderate: {floor: 50000,  ceiling: 200000}
              severe:   {floor: 200000, ceiling: 800000}
        """,
    )
    with pytest.raises(ValueError) as exc_info:
        load_market_data(path)
    assert "unsupported schema version" in str(exc_info.value)


def test_missing_severity_raises(tmp_path: Path) -> None:
    """Every claim_type must declare all three severities."""
    path = _write_yaml(
        tmp_path,
        """
        version: 1
        claim_types:
          water_damage:
            severity_bands:
              minor:    {max_amount: 50000}
              severe:   {max_amount: null}
            ranges:
              minor:    {floor: 5000,   ceiling: 50000}
              severe:   {floor: 200000, ceiling: 800000}
        """,
    )
    with pytest.raises(ValueError) as exc_info:
        load_market_data(path)
    assert "missing severity_bands.moderate" in str(exc_info.value)


def test_ceiling_below_floor_raises(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        version: 1
        claim_types:
          water_damage:
            severity_bands:
              minor:    {max_amount: 50000}
              moderate: {max_amount: 150000}
              severe:   {max_amount: null}
            ranges:
              minor:    {floor: 5000,   ceiling: 50000}
              moderate: {floor: 200000, ceiling: 50000}
              severe:   {floor: 200000, ceiling: 800000}
        """,
    )
    with pytest.raises(ValueError) as exc_info:
        load_market_data(path)
    assert "ceiling < floor" in str(exc_info.value)


def test_market_range_validates_negative_bounds() -> None:
    """`MarketRange` itself rejects negative floor/ceiling at the Pydantic boundary."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MarketRange(
            claim_type="water_damage",
            severity="minor",
            floor=Decimal("-1"),
            ceiling=Decimal("100"),
        )


def test_contains_is_inclusive_on_both_ends() -> None:
    """`MarketRange.contains` is inclusive on both bounds — locked behaviour."""
    r = MarketRange(
        claim_type="fire",
        severity="severe",
        floor=Decimal("500000"),
        ceiling=Decimal("1500000"),
    )
    assert r.contains(Decimal("500000")) is True
    assert r.contains(Decimal("1500000")) is True
    assert r.contains(Decimal("499999.99")) is False
    assert r.contains(Decimal("1500000.01")) is False
