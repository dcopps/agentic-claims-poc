"""
Settings model — single source of truth for runtime configuration.

Strategy: defaults live in the Pydantic model below. A YAML overlay (loaded
from `backend/settings.yaml` if present) supplies environment-specific
overrides. Environment variables override both. CLI flags will layer on top
in later phases when there's a CLI to attach them to.

Phase 0 surface area is deliberately minimal — `app_name`, `environment`,
`api_host`, `api_port`, `log_level`, `cors_allowed_origins`. Phase 1 adds
nested sub-models for database, LLM providers, embeddings, observability,
and escalation. The `_load_yaml_overrides` helper is written so nesting
extends the same loader without rewriting it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the YAML overlay relative to this file. Phase 0 keeps this static;
# Phase 1+ may make the path configurable for multi-environment overlays.
_SETTINGS_YAML_PATH = Path(__file__).parent / "settings.yaml"

# Maximum bytes we'll read from the YAML overlay before refusing. Defensive
# guard against accidentally pointing the path at a huge file.
_MAX_YAML_BYTES = 256 * 1024


class Settings(BaseSettings):
    """Runtime configuration for the backend."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_nested_delimiter="__",
        extra="forbid",
    )

    app_name: str = Field(default="agentic-claims-poc")
    environment: Literal["dev", "staging", "prod"] = Field(default="dev")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @model_validator(mode="before")
    @classmethod
    def _apply_yaml_overlay(cls, values: Any) -> Any:
        """Merge YAML overlay before field validation runs."""
        # Only merge dict-shaped initial values — Pydantic also passes model
        # instances when revalidating; we do nothing in that case.
        if not isinstance(values, dict):
            return values
        overlay = _load_yaml_overrides(_SETTINGS_YAML_PATH)
        merged = {**overlay, **values}
        return merged


def _load_yaml_overrides(path: Path) -> dict[str, Any]:
    """
    Defensively load YAML overrides from `path`.

    Sanitise → validate → abort → execute:
      1. Sanitise: resolve to an absolute path.
      2. Validate: file exists, is readable, is below the size cap, parses
         as a YAML mapping.
      3. Abort: raise `ValueError` with diagnostic context on any failure.
         No silent fallback — if the file exists but is malformed, the
         caller must know.
      4. Execute: return the parsed mapping (empty dict if the file is
         absent — that's the documented "no overlay" state, not a failure).
    """
    resolved = path.expanduser().resolve()

    # Absent overlay is a legitimate state — defaults stand alone.
    if not resolved.exists():
        return {}

    if not resolved.is_file():
        raise ValueError(
            f"settings.yaml overlay path is not a regular file: {resolved}"
        )

    size = resolved.stat().st_size
    if size > _MAX_YAML_BYTES:
        raise ValueError(
            f"settings.yaml overlay too large: {size} bytes at {resolved} "
            f"(cap is {_MAX_YAML_BYTES} bytes — refusing to load)"
        )

    raw = resolved.read_text(encoding="utf-8")

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        # Surface the parser error with the path so the failure is traceable
        # without re-running. Truncate the YAML body in the message; full
        # content remains in the file on disk.
        excerpt = raw[:500]
        raise ValueError(
            f"settings.yaml overlay at {resolved} is not valid YAML: "
            f"{exc} | first 500 chars: {excerpt!r}"
        ) from exc

    # An empty YAML file parses to None; treat as "no overlay".
    if parsed is None:
        return {}

    if not isinstance(parsed, dict):
        raise ValueError(
            f"settings.yaml overlay at {resolved} must parse to a mapping; "
            f"got {type(parsed).__name__}"
        )

    return parsed
