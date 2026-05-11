"""
Tests for `backend.app.logging.api_logger`.

Covers the APICallRecord round-trip, the redactor hook, the excerpt
budget, the disabled-logger no-op, the error-path record shape, the
sidecar file sink, and `compute_cost_usd`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.logging import APICallRecord, APILogger, compute_cost_usd
from backend.app.logging.api_logger import (
    coerce_error,
    make_excerpt,
)


def _record(**overrides: object) -> APICallRecord:
    """Build a default-valid record; overrides replace individual fields."""
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "correlation_id": uuid4(),
        "agent": "validator",
        "step": "coverage_check",
        "provider": "mistral",
        "model": "mistral-large-latest",
        "system_prompt_excerpt": "sys",
        "user_prompt_excerpt": "usr",
        "response_excerpt": "rsp",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cost_usd": None,
        "latency_ms": 42,
        "started_at": now,
        "completed_at": now,
        "error": None,
    }
    base.update(overrides)
    return APICallRecord(**base)  # type: ignore[arg-type]


def test_log_call_emits_one_canonical_json_line() -> None:
    captured: list[str] = []
    logger = APILogger(enabled=True, excerpt_chars=200, sink=captured.append)
    logger.log_call(_record())
    assert len(captured) == 1
    parsed = json.loads(captured[0])
    assert parsed["agent"] == "validator"
    assert parsed["step"] == "coverage_check"
    assert parsed["provider"] == "mistral"
    assert parsed["error"] is None


def test_disabled_logger_emits_nothing() -> None:
    captured: list[str] = []
    logger = APILogger(enabled=False, excerpt_chars=200, sink=captured.append)
    logger.log_call(_record())
    assert captured == []


def test_error_path_records_type_and_message() -> None:
    captured: list[str] = []
    logger = APILogger(enabled=True, excerpt_chars=200, sink=captured.append)
    exc = RuntimeError("downstream timed out")
    logger.log_call(_record(error=coerce_error(exc)))
    parsed = json.loads(captured[0])
    assert parsed["error"] == {"type": "RuntimeError", "message": "downstream timed out"}


def test_redactor_is_applied_via_excerpt_helper() -> None:
    def redact(s: str) -> str:
        return s.replace("secret", "[REDACTED]")

    logger = APILogger(
        enabled=True, excerpt_chars=200, sink=lambda _l: None, redactor=redact
    )
    out = logger.excerpt("this is a secret message")
    assert "[REDACTED]" in out
    assert "secret" not in out


def test_excerpt_truncates_to_budget() -> None:
    logger = APILogger(enabled=True, excerpt_chars=10, sink=lambda _l: None)
    out = logger.excerpt("0123456789ABCDEFGHIJKLMN")
    assert out.startswith("0123456789")
    assert "truncated" in out


def test_file_sink_appends_lines(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / "api.ndjson"
    captured: list[str] = []
    logger = APILogger(
        enabled=True,
        excerpt_chars=200,
        sink=captured.append,
        file_path=target,
    )
    logger.log_call(_record())
    logger.log_call(_record())
    contents = target.read_text(encoding="utf-8").splitlines()
    assert len(contents) == 2
    for line in contents:
        assert json.loads(line)["agent"] == "validator"


def test_record_rejects_negative_tokens() -> None:
    with pytest.raises(Exception) as exc_info:
        _record(prompt_tokens=-1)
    assert "greater than or equal to 0" in str(exc_info.value).lower()


def test_make_excerpt_short_input_returns_verbatim() -> None:
    assert make_excerpt("hello", 100, lambda s: s) == "hello"


def test_make_excerpt_rejects_zero_budget() -> None:
    with pytest.raises(ValueError):
        make_excerpt("hello", 0, lambda s: s)


def test_compute_cost_usd_returns_none_when_rate_missing() -> None:
    assert (
        compute_cost_usd(
            pricing={},
            model="anything",
            prompt_tokens=1_000,
            completion_tokens=500,
        )
        is None
    )


def test_compute_cost_usd_uses_per_million_rates() -> None:
    cost = compute_cost_usd(
        pricing={"m": (Decimal("2.00"), Decimal("6.00"))},
        model="m",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
    )
    # 1M * 2.00 + 0.5M * 6.00 = 2 + 3 = 5.00
    assert cost == pytest.approx(5.00, rel=1e-6)


def test_compute_cost_usd_rejects_negative_rate() -> None:
    with pytest.raises(ValueError):
        compute_cost_usd(
            pricing={"m": (Decimal("-1"), Decimal("1"))},
            model="m",
            prompt_tokens=1,
            completion_tokens=1,
        )


def test_apilogger_rejects_zero_excerpt_chars() -> None:
    with pytest.raises(ValueError):
        APILogger(enabled=True, excerpt_chars=0, sink=lambda _l: None)
