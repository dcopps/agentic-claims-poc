"""
Market-data lookup for the Adjuster agent.

The Adjuster does not invent settlement ranges; it looks them up in a
static `(claim_type, severity)` table supplied by `market_data.yaml`
and instructs the LLM to pick a value *within* the looked-up range.
Severity is derived deterministically here from the reported amount —
the LLM is never asked to classify severity.

Public surface:

  - `MarketRange` — the typed range that the Adjuster passes into its
    prompt and re-validates the model's chosen value against.
  - `MarketDataTable` — the loaded table, exposing one method
    (`lookup`) that combines severity derivation and range retrieval.
  - `load_market_data(path)` — read + parse + validate a YAML file
    into a `MarketDataTable`. Cached at module level per resolved
    path so repeated calls do not re-parse YAML.

Defensive ordering throughout: sanitise → validate → abort → execute.
Every guard has a triggering test. No silent fallbacks.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Severity band keys are pinned. Adding a new severity would require
# every downstream consumer to know about it; the literal serves as a
# typo-prevention guard at config-load time.
Severity = Literal["minor", "moderate", "severe"]
_SEVERITY_ORDER: tuple[Severity, ...] = ("minor", "moderate", "severe")

# The schema version this loader understands. Bumping the YAML's
# `version` field signals an incompatible change; the loader refuses
# anything else rather than silently misinterpreting an evolved
# structure.
_SUPPORTED_SCHEMA_VERSION = 1

# Hard cap on the YAML file size — a 6×3 lookup is ~3 KB, so anything
# above this cap is almost certainly a misconfiguration (the wrong
# file path got plumbed in). The error includes the actual bytes seen.
_MAX_MARKET_DATA_BYTES = 64 * 1024


class MarketRange(BaseModel):
    """One cell of the lookup table."""

    model_config = ConfigDict(extra="forbid")

    claim_type: str = Field(min_length=1, max_length=64)
    severity: Severity
    floor: Decimal = Field(ge=Decimal("0"))
    ceiling: Decimal = Field(ge=Decimal("0"))

    def contains(self, value: Decimal) -> bool:
        """Inclusive containment check used by the Adjuster's parse guard."""
        return self.floor <= value <= self.ceiling


class _SeverityBand(BaseModel):
    """Severity-derivation rule for one band of one claim_type."""

    model_config = ConfigDict(extra="forbid")

    # `None` means "unbounded upper" — only valid for the last band in
    # declaration order. The post-load validator enforces that.
    max_amount: Decimal | None


class _ClaimTypeEntry(BaseModel):
    """One claim_type's bands and ranges, as parsed from YAML."""

    model_config = ConfigDict(extra="forbid")

    severity_bands: dict[Severity, _SeverityBand]
    ranges: dict[Severity, dict[str, Decimal]]


class MarketDataTable:
    """
    The loaded market-data table.

    Construct via `load_market_data(path)` — the constructor itself
    accepts the validated `_ClaimTypeEntry` mapping and is not meant
    for direct use outside this module.
    """

    def __init__(self, claim_types: dict[str, _ClaimTypeEntry]) -> None:
        self._claim_types = claim_types

    def supported_claim_types(self) -> list[str]:
        """Return the sorted list of supported claim_type identifiers."""
        return sorted(self._claim_types.keys())

    def lookup(self, *, claim_type: str, reported_amount: Decimal) -> MarketRange:
        """
        Resolve `(claim_type, severity)` to a `MarketRange`.

        Severity is derived from `reported_amount` using the bands
        declared for the claim_type. Order of operations matches the
        documented defensive sequence:

          1. Sanitise: lowercase + strip the claim_type identifier so
             a stray "Water_Damage  " from a model normalises to the
             canonical key without a typo-driven miss.
          2. Validate: claim_type exists in the table; reported_amount
             is strictly positive.
          3. Abort: `ValueError` with the unknown type and the
             supported set, or with the rejected amount.
          4. Execute: walk severity bands in declaration order; the
             first whose `max_amount` is null or `>=` reported_amount
             wins. Construct and return the typed `MarketRange`.
        """
        cleaned = claim_type.strip().lower()
        if not cleaned:
            raise ValueError(
                "MarketDataTable.lookup: claim_type is empty or whitespace"
            )

        entry = self._claim_types.get(cleaned)
        if entry is None:
            raise ValueError(
                "MarketDataTable.lookup: unknown claim_type "
                f"{claim_type!r} (normalised={cleaned!r}); supported types="
                f"{self.supported_claim_types()}"
            )

        if reported_amount <= Decimal("0"):
            raise ValueError(
                "MarketDataTable.lookup: reported_amount must be positive; "
                f"got {reported_amount}"
            )

        severity = _derive_severity(entry.severity_bands, reported_amount)
        # Post-precondition: every claim_type's `ranges` dict is fully
        # populated for all three severities by `_validate_table_shape`,
        # so the lookup below is guaranteed to hit.
        range_block = entry.ranges[severity]
        return MarketRange(
            claim_type=cleaned,
            severity=severity,
            floor=range_block["floor"],
            ceiling=range_block["ceiling"],
        )


def load_market_data(path: Path) -> MarketDataTable:
    """
    Load and validate a market-data YAML file.

    Cached at module level per resolved path so repeated agents
    constructed with the same path do not re-parse YAML on every
    call. Tests clear the cache via `clear_market_data_cache()`.
    """
    resolved = path.expanduser().resolve()
    return _load_market_data_cached(resolved)


def clear_market_data_cache() -> None:
    """Drop the loader cache. Used by tests that edit the YAML between runs."""
    _load_market_data_cached.cache_clear()


# --------------------------------------------------------------------------- #
# Internal helpers — module-private; do not import from outside.
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=8)
def _load_market_data_cached(resolved: Path) -> MarketDataTable:
    """Cached read-and-validate. Keyed on the resolved (absolute) path."""
    raw = _read_yaml(resolved)
    _validate_top_level_shape(raw, resolved)
    claim_types_block = raw["claim_types"]
    if not isinstance(claim_types_block, dict) or not claim_types_block:
        raise ValueError(
            f"market_data.yaml at {resolved}: top-level 'claim_types' must be a "
            f"non-empty mapping; got {type(claim_types_block).__name__}"
        )

    entries: dict[str, _ClaimTypeEntry] = {}
    for raw_name, raw_entry in claim_types_block.items():
        name = _normalise_claim_type_key(raw_name, resolved)
        entry = _parse_claim_type_entry(name, raw_entry, resolved)
        entries[name] = entry

    _validate_table_shape(entries, resolved)
    return MarketDataTable(entries)


def _read_yaml(resolved: Path) -> dict[str, Any]:
    if not resolved.exists():
        raise FileNotFoundError(
            f"market_data.yaml: file does not exist at {resolved}"
        )
    if not resolved.is_file():
        raise ValueError(
            f"market_data.yaml: path is not a regular file: {resolved}"
        )
    size = resolved.stat().st_size
    if size == 0:
        raise ValueError(
            f"market_data.yaml: file is empty at {resolved} — refusing to load"
        )
    if size > _MAX_MARKET_DATA_BYTES:
        raise ValueError(
            "market_data.yaml: file exceeds size cap; "
            f"path={resolved} size={size} cap={_MAX_MARKET_DATA_BYTES}"
        )

    text = resolved.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"market_data.yaml at {resolved}: YAML parse error: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"market_data.yaml at {resolved}: top level must be a mapping; "
            f"got {type(parsed).__name__}"
        )
    return parsed


def _validate_top_level_shape(raw: dict[str, Any], resolved: Path) -> None:
    version = raw.get("version")
    if version != _SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"market_data.yaml at {resolved}: unsupported schema version "
            f"{version!r}; this loader expects version={_SUPPORTED_SCHEMA_VERSION}"
        )
    if "claim_types" not in raw:
        raise ValueError(
            f"market_data.yaml at {resolved}: required key 'claim_types' missing"
        )


def _normalise_claim_type_key(raw_name: Any, resolved: Path) -> str:
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(
            f"market_data.yaml at {resolved}: claim_type keys must be "
            f"non-empty strings; got {raw_name!r}"
        )
    return raw_name.strip().lower()


def _parse_claim_type_entry(
    name: str, raw_entry: Any, resolved: Path
) -> _ClaimTypeEntry:
    if not isinstance(raw_entry, dict):
        raise ValueError(
            f"market_data.yaml at {resolved}: entry for claim_type {name!r} "
            f"must be a mapping; got {type(raw_entry).__name__}"
        )

    bands_raw = raw_entry.get("severity_bands")
    ranges_raw = raw_entry.get("ranges")
    if not isinstance(bands_raw, dict) or not isinstance(ranges_raw, dict):
        raise ValueError(
            f"market_data.yaml at {resolved}: entry for claim_type {name!r} "
            "must contain mapping fields 'severity_bands' and 'ranges'"
        )

    bands: dict[Severity, _SeverityBand] = {}
    for severity, band_raw in bands_raw.items():
        if severity not in _SEVERITY_ORDER:
            raise ValueError(
                f"market_data.yaml at {resolved}: unknown severity "
                f"{severity!r} in claim_type {name!r}; expected one of "
                f"{list(_SEVERITY_ORDER)}"
            )
        if not isinstance(band_raw, dict):
            raise ValueError(
                f"market_data.yaml at {resolved}: severity_bands.{severity} "
                f"in claim_type {name!r} must be a mapping; "
                f"got {type(band_raw).__name__}"
            )
        max_amount = _coerce_optional_decimal(
            band_raw.get("max_amount"),
            where=f"severity_bands.{severity}.max_amount of {name!r}",
            resolved=resolved,
        )
        bands[severity] = _SeverityBand(max_amount=max_amount)

    ranges: dict[Severity, dict[str, Decimal]] = {}
    for severity, range_raw in ranges_raw.items():
        if severity not in _SEVERITY_ORDER:
            raise ValueError(
                f"market_data.yaml at {resolved}: unknown severity "
                f"{severity!r} in ranges of claim_type {name!r}; expected one "
                f"of {list(_SEVERITY_ORDER)}"
            )
        if not isinstance(range_raw, dict):
            raise ValueError(
                f"market_data.yaml at {resolved}: ranges.{severity} in "
                f"claim_type {name!r} must be a mapping; "
                f"got {type(range_raw).__name__}"
            )
        floor = _coerce_required_decimal(
            range_raw.get("floor"),
            where=f"ranges.{severity}.floor of {name!r}",
            resolved=resolved,
        )
        ceiling = _coerce_required_decimal(
            range_raw.get("ceiling"),
            where=f"ranges.{severity}.ceiling of {name!r}",
            resolved=resolved,
        )
        if ceiling < floor:
            raise ValueError(
                f"market_data.yaml at {resolved}: ranges.{severity} of "
                f"claim_type {name!r} has ceiling < floor "
                f"(floor={floor}, ceiling={ceiling})"
            )
        ranges[severity] = {"floor": floor, "ceiling": ceiling}

    return _ClaimTypeEntry(severity_bands=bands, ranges=ranges)


def _validate_table_shape(
    entries: dict[str, _ClaimTypeEntry], resolved: Path
) -> None:
    """
    Post-load shape checks that the per-entry parser cannot do alone.

    Each claim_type must declare *all three* severities in both
    `severity_bands` and `ranges`, and only the last band in
    declaration order may have a null `max_amount` (the unbounded
    upper bin). Without these checks a missing severity would surface
    as a `KeyError` deep inside `MarketDataTable.lookup`.
    """
    for name, entry in entries.items():
        for severity in _SEVERITY_ORDER:
            if severity not in entry.severity_bands:
                raise ValueError(
                    f"market_data.yaml at {resolved}: claim_type {name!r} "
                    f"is missing severity_bands.{severity}"
                )
            if severity not in entry.ranges:
                raise ValueError(
                    f"market_data.yaml at {resolved}: claim_type {name!r} "
                    f"is missing ranges.{severity}"
                )

        # Only the last band may have max_amount=null. Any other null is
        # ambiguous — what's the upper bound for the next band? — and we
        # refuse rather than guess.
        for severity in _SEVERITY_ORDER[:-1]:
            band = entry.severity_bands[severity]
            if band.max_amount is None:
                raise ValueError(
                    f"market_data.yaml at {resolved}: claim_type {name!r} "
                    f"has null max_amount for severity_bands.{severity}; "
                    "only the last severity (in declaration order) may be "
                    "unbounded"
                )


def _coerce_optional_decimal(
    value: Any, *, where: str, resolved: Path
) -> Decimal | None:
    if value is None:
        return None
    return _coerce_required_decimal(value, where=where, resolved=resolved)


def _coerce_required_decimal(value: Any, *, where: str, resolved: Path) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # YAML happily parses 1.5e6 as a float — we accept it but route
        # through `str` so the Decimal carries no float-binary noise.
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(
                f"market_data.yaml at {resolved}: {where} must be a number "
                f"or numeric string; got {value!r}"
            ) from exc
    raise ValueError(
        f"market_data.yaml at {resolved}: {where} must be a number, integer, "
        f"or numeric string; got {type(value).__name__}"
    )


def _derive_severity(
    bands: dict[Severity, _SeverityBand], reported_amount: Decimal
) -> Severity:
    """
    Walk severities in canonical order; return the first band whose
    `max_amount` is null or `>=` the reported amount.

    The shape-validator guarantees all three severities are present
    and that only the last is allowed to be unbounded, so this loop
    is guaranteed to return.
    """
    for severity in _SEVERITY_ORDER:
        band = bands[severity]
        if band.max_amount is None or reported_amount <= band.max_amount:
            return severity
    # The unbounded-upper invariant means this is unreachable. The
    # explicit raise is here only to satisfy the type checker (Severity
    # is a Literal, not Optional) and as a guard against a future
    # refactor that breaks the invariant.
    raise AssertionError(
        "_derive_severity: walked past the last band — shape invariant broken"
    )
