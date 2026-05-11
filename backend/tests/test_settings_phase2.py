"""
Tests for the Phase 2 Settings additions: LoggingSettings,
RetrievalSettings, and the new fields on LLMSettings.

Every guard clause gets a triggering test that asserts on the
ValidationError message content.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.settings import (
    LLMSettings,
    LoggingSettings,
    RetrievalSettings,
)

# --------------------------------------------------------------------------- #
# LoggingSettings
# --------------------------------------------------------------------------- #


def test_logging_settings_defaults() -> None:
    cfg = LoggingSettings()
    assert cfg.api_log_enabled is True
    assert cfg.api_log_excerpt_chars == 2000
    assert cfg.api_log_path is None


def test_logging_settings_rejects_excerpt_chars_below_floor() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LoggingSettings(api_log_excerpt_chars=50)
    assert "greater than or equal to 100" in str(exc_info.value).lower()


def test_logging_settings_rejects_excerpt_chars_above_ceiling() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LoggingSettings(api_log_excerpt_chars=99_999)
    assert "less than or equal to 20000" in str(exc_info.value).lower()


def test_logging_settings_accepts_file_path() -> None:
    cfg = LoggingSettings(api_log_path=Path("/tmp/api.ndjson"))
    assert cfg.api_log_path == Path("/tmp/api.ndjson")


# --------------------------------------------------------------------------- #
# RetrievalSettings
# --------------------------------------------------------------------------- #


def test_retrieval_settings_defaults() -> None:
    cfg = RetrievalSettings()
    assert cfg.policy_source_path == Path("backend/data/sample_policy.txt")
    assert cfg.top_k == 3


def test_retrieval_settings_rejects_top_k_zero() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RetrievalSettings(top_k=0)
    assert "greater than or equal to 1" in str(exc_info.value).lower()


def test_retrieval_settings_rejects_top_k_above_ceiling() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RetrievalSettings(top_k=999)
    assert "less than or equal to 20" in str(exc_info.value).lower()


# --------------------------------------------------------------------------- #
# LLMSettings — new fields
# --------------------------------------------------------------------------- #


def test_llm_settings_defaults() -> None:
    cfg = LLMSettings()
    assert cfg.validator_max_tokens == 1024
    assert cfg.validator_temperature == pytest.approx(0.1)
    assert cfg.request_timeout_s == pytest.approx(60.0)
    assert cfg.pricing == {}


def test_llm_settings_rejects_temperature_above_one() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LLMSettings(validator_temperature=2.0)
    assert "less than or equal to 1" in str(exc_info.value).lower()


def test_llm_settings_rejects_negative_temperature() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LLMSettings(validator_temperature=-0.1)
    assert "greater than or equal to 0" in str(exc_info.value).lower()


def test_llm_settings_rejects_zero_max_tokens() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LLMSettings(validator_max_tokens=0)
    assert "greater than or equal to 1" in str(exc_info.value).lower()


def test_llm_settings_rejects_timeout_below_one_second() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LLMSettings(request_timeout_s=0.5)
    assert "greater than or equal to 1" in str(exc_info.value).lower()


def test_llm_settings_accepts_pricing_table() -> None:
    cfg = LLMSettings(
        pricing={
            "mistral-large-latest": (Decimal("2.00"), Decimal("6.00")),
        }
    )
    rate = cfg.pricing["mistral-large-latest"]
    assert rate == (Decimal("2.00"), Decimal("6.00"))
