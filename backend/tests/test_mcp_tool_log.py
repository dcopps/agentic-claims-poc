"""
The tool-call log: the repository, the recorder, and `run_logged`'s three exits.

Database-backed: the row must really land, `recent` must really order, and the
token value must appear nowhere in what is stored or logged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import SecretStr

from backend.app.mcp.activity import ActivityBus
from backend.app.mcp.instrument import ToolCall, not_found, run_logged
from backend.app.mcp.models import TargetRef, ToolCallRecord
from backend.app.mcp.tool_log import ToolCallRecorder, ToolCallRepository, format_log_line
from backend.settings import MCPSettings, Settings

_TOKEN = "super-secret-token-value"


def _record(tool: str = "get_run", *, call_id: int | None = None) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        called_at=datetime.now(UTC),
        tool=tool,
        arguments={"correlation_id": "abc"},
        target=TargetRef(kind="run", id=uuid4()),
        caller="shared-token",
        outcome="ok",
        error_class=None,
        latency_ms=12,
    )


async def _first(bus: ActivityBus) -> ToolCallRecord:
    async for record in bus.subscribe():
        return record
    raise AssertionError("the subscription ended without a record")


def _settings_with_token(db_settings: Settings) -> Settings:
    return db_settings.model_copy(update={"mcp": MCPSettings(shared_token=SecretStr(_TOKEN))})


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #


def test_insert_returns_the_stored_row(clean_db: psycopg.Connection) -> None:
    stored = ToolCallRepository.insert(clean_db, _record())
    assert stored.call_id == 1
    assert stored.tool == "get_run"
    assert stored.target is not None and stored.target.kind == "run"
    assert stored.arguments == {"correlation_id": "abc"}


def test_insert_refuses_an_already_stored_record(clean_db: psycopg.Connection) -> None:
    with pytest.raises(ValueError, match="already stored as call_id=7"):
        ToolCallRepository.insert(clean_db, _record(call_id=7))


def test_recent_returns_the_last_n_ascending(clean_db: psycopg.Connection) -> None:
    for name in ("a", "b", "c", "d"):
        ToolCallRepository.insert(clean_db, _record(name))
    recent = ToolCallRepository.recent(clean_db, 2)
    assert [r.tool for r in recent] == ["c", "d"]
    assert [r.call_id for r in recent] == [3, 4]
    assert ToolCallRepository.recent(clean_db, 0) == []
    with pytest.raises(ValueError, match="limit must be >= 0; got -1"):
        ToolCallRepository.recent(clean_db, -1)


def test_half_a_target_is_refused_by_the_table(clean_db: psycopg.Connection) -> None:
    with clean_db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO mcp_tool_calls (called_at, tool, arguments, target_kind, target_id, "
            "caller, outcome, error_class, latency_ms) "
            "VALUES (now(), 't', '{}', 'run', NULL, 'c', 'ok', NULL, 0)"
        )


# --------------------------------------------------------------------------- #
# Recorder and run_logged
# --------------------------------------------------------------------------- #


def test_recorder_stores_logs_and_publishes(
    clean_db: psycopg.Connection, db_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario() -> tuple[ToolCallRecord, ToolCallRecord]:
        bus = ActivityBus(queue_maxsize=5)
        recorder = ToolCallRecorder(settings=_settings_with_token(db_settings), bus=bus)
        waiter = asyncio.create_task(_first(bus))
        await asyncio.sleep(0)
        with caplog.at_level(logging.INFO, logger="backend.app.mcp.calls"):
            stored = await recorder.record(_record("list_claims"))
        published = await waiter
        return stored, published

    stored, published = asyncio.run(scenario())
    assert stored.call_id is not None and published.call_id == stored.call_id
    assert ToolCallRepository.recent(clean_db, 1)[0].tool == "list_claims"
    line = next(r.message for r in caplog.records if r.name == "backend.app.mcp.calls")
    assert '"tool": "list_claims"' in line
    assert _TOKEN not in line and _TOKEN not in format_log_line(stored)


def test_run_logged_ok_path(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    async def scenario() -> str:
        recorder = ToolCallRecorder(settings=db_settings, bus=ActivityBus(queue_maxsize=5))
        call = ToolCall("get_claim", {"claim_id": "x"}, TargetRef(kind="claim", id=uuid4()))

        async def body() -> str:
            return "fine"

        return await run_logged(recorder, "shared-token", call, body)

    assert asyncio.run(scenario()) == "fine"
    row = ToolCallRepository.recent(clean_db, 1)[0]
    assert (row.tool, row.outcome, row.error_class, row.caller) == (
        "get_claim",
        "ok",
        None,
        "shared-token",
    )
    assert row.latency_ms >= 0


def test_run_logged_not_found_is_recorded_and_re_raised(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    missing = uuid4()

    async def scenario() -> None:
        recorder = ToolCallRecorder(settings=db_settings, bus=ActivityBus(queue_maxsize=5))
        call = ToolCall("get_run", {"correlation_id": str(missing)})

        async def body() -> None:
            raise not_found("run", missing)

        await run_logged(recorder, "shared-token", call, body)

    with pytest.raises(ToolError, match=f"not_found: run {missing}"):
        asyncio.run(scenario())
    row = ToolCallRepository.recent(clean_db, 1)[0]
    assert (row.outcome, row.error_class) == ("error", "ToolError")


def test_run_logged_unexpected_exception_hides_the_message(
    clean_db: psycopg.Connection, db_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario() -> None:
        recorder = ToolCallRecorder(settings=db_settings, bus=ActivityBus(queue_maxsize=5))
        call = ToolCall("get_run", {"correlation_id": "x"})

        async def body() -> None:
            raise KeyError("internal detail that must not leak")

        await run_logged(recorder, "shared-token", call, body)

    with caplog.at_level(logging.ERROR), pytest.raises(ToolError) as excinfo:
        asyncio.run(scenario())
    assert str(excinfo.value) == "internal_error: KeyError"
    assert "must not leak" not in str(excinfo.value)
    assert "must not leak" in caplog.text  # the operator's log has it
    row = ToolCallRepository.recent(clean_db, 1)[0]
    assert (row.outcome, row.error_class) == ("error", "KeyError")
