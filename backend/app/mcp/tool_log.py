"""
The tool-call log — the persisted record of who asked what of the system.

Three sinks, one shape (`ToolCallRecord`):

  1. **The table** `mcp_tool_calls` (migration 0003) — the governance record,
     and what the activity feed replays on connect.
  2. **A structured log line** on the `backend.app.mcp.calls` logger — so the
     Render log viewer and Application Insights carry the same record.
  3. **The activity bus** — the live feed.

The write is the first of the three: a record that could not be persisted is
not announced as if it had been. A failed write raises to the tool wrapper,
which surfaces it; the log is a requirement of the design, not a nice-to-have,
so it is never swallowed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from backend.app.mcp.activity import ActivityBus
from backend.app.mcp.models import TargetRef, ToolCallRecord
from backend.db.connection import open_connection
from backend.settings import Settings

# Every record line goes through this logger name so a deployment can route or
# filter the access record independently of application logs.
_CALLS_LOGGER_NAME = "backend.app.mcp.calls"
_calls_logger = logging.getLogger(_CALLS_LOGGER_NAME)

_COLUMNS = (
    "call_id, called_at, tool, arguments, target_kind, target_id, caller, "
    "outcome, error_class, latency_ms"
)


class ToolCallRepository:
    """Connection-scoped insert and recent-rows read over `mcp_tool_calls`."""

    @staticmethod
    def insert(conn: psycopg.Connection, record: ToolCallRecord) -> ToolCallRecord:
        """Persist `record` and return it with the `call_id` the table assigned."""
        # A record that already carries an id was stored once; storing it again
        # would duplicate the access record, so refuse rather than guess.
        if record.call_id is not None:
            raise ValueError(
                f"ToolCallRepository.insert: record already stored as call_id={record.call_id}"
            )
        target = record.target
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO mcp_tool_calls (
                    called_at, tool, arguments, target_kind, target_id, caller,
                    outcome, error_class, latency_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_COLUMNS}
                """,
                (
                    record.called_at,
                    record.tool,
                    Jsonb(record.arguments),
                    target.kind if target is not None else None,
                    target.id if target is not None else None,
                    record.caller,
                    record.outcome,
                    record.error_class,
                    record.latency_ms,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise RuntimeError("ToolCallRepository.insert: INSERT...RETURNING produced no row")
        return _row_to_record(row)

    @staticmethod
    def recent(conn: psycopg.Connection, limit: int) -> list[ToolCallRecord]:
        """The last `limit` records in ascending `call_id` order; `[]` for a limit of 0."""
        if limit < 0:
            raise ValueError(f"ToolCallRepository.recent: limit must be >= 0; got {limit}")
        if limit == 0:
            return []
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNS} FROM (SELECT {_COLUMNS} FROM mcp_tool_calls "
                "ORDER BY call_id DESC LIMIT %s) AS newest ORDER BY call_id",
                (limit,),
            )
            rows = cur.fetchall()
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: tuple[Any, ...]) -> ToolCallRecord:
    target = TargetRef(kind=row[4], id=row[5]) if row[4] is not None else None
    return ToolCallRecord(
        call_id=row[0],
        called_at=row[1],
        tool=row[2],
        arguments=row[3],
        target=target,
        caller=row[6],
        outcome=row[7],
        error_class=row[8],
        latency_ms=row[9],
    )


def format_log_line(record: ToolCallRecord) -> str:
    """The record as one sorted-key JSON line, the same style as the API logger."""
    return json.dumps(record.model_dump(mode="json"), sort_keys=True, default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"format_log_line: unserialisable value of type {type(value).__name__}")


class ToolCallRecorder:
    """Persist, log and broadcast a record, in that order, from the event loop."""

    def __init__(self, *, settings: Settings, bus: ActivityBus) -> None:
        self._settings = settings
        self._bus = bus

    async def record(self, record: ToolCallRecord) -> ToolCallRecord:
        """Store `record`, emit its log line, publish it; return the stored copy."""
        stored = await run_in_threadpool(self._insert, record)
        _calls_logger.info(format_log_line(stored))
        self._bus.publish(stored)
        return stored

    def _insert(self, record: ToolCallRecord) -> ToolCallRecord:
        with open_connection(self._settings) as conn:
            return ToolCallRepository.insert(conn, record)
