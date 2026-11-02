"""
The wrapper every tool body runs inside.

One place decides what a client sees on failure and guarantees a record on
every exit path:

  - A **structured refusal** (`ToolError`, e.g. `not_found: run …`) reaches the
    client as an `is_error` result with that text, and is recorded as an error
    with its class.
  - **Any other exception** is a defect. It is logged with its traceback here,
    recorded with its class, and re-raised as `ToolError("internal_error: …")`
    carrying the class name only — a client never receives a traceback or an
    exception message that might quote internal state.
  - **Success** is recorded as `ok`.

Latency is measured around the body. The record is written after the body,
so a tool that is still running has no row yet — the feed shows completed
calls, which is what "what was asked, and what came back" means.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypeVar
from uuid import UUID

from mcp.server.mcpserver.exceptions import ToolError

from backend.app.mcp.models import TargetKind, TargetRef, ToolCallRecord
from backend.app.mcp.tool_log import ToolCallRecorder

_logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ToolCall:
    """
    What is known about a call before its body runs — and the one thing the
    body may add: the target it created (`run_scenario` learns its run id only
    once the pipeline has started).
    """

    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    target: TargetRef | None = None


def not_found(kind: TargetKind, identifier: UUID) -> ToolError:
    """The one refusal shape for an unknown id: `not_found: run <id>`."""
    return ToolError(f"not_found: {kind} {identifier}")


async def run_logged(
    recorder: ToolCallRecorder,
    caller: str,
    call: ToolCall,
    body: Callable[[], Awaitable[T]],
) -> T:
    """Run `body`, then record the call with its outcome, whatever the outcome."""
    started_at = datetime.now(UTC)
    clock = perf_counter()
    try:
        result = await body()
    except ToolError as exc:
        await recorder.record(_record(call, caller, started_at, clock, "error", exc))
        raise
    except Exception as exc:
        # The traceback belongs in the server log, where an operator reads it;
        # the client gets the class name and nothing else.
        _logger.exception("mcp tool %s failed: %s", call.tool, type(exc).__name__)
        await recorder.record(_record(call, caller, started_at, clock, "error", exc))
        raise ToolError(f"internal_error: {type(exc).__name__}") from exc
    await recorder.record(_record(call, caller, started_at, clock, "ok", None))
    return result


def _record(
    call: ToolCall,
    caller: str,
    started_at: datetime,
    clock: float,
    outcome: str,
    error: BaseException | None,
) -> ToolCallRecord:
    return ToolCallRecord(
        called_at=started_at,
        tool=call.tool,
        arguments=call.arguments,
        target=call.target,
        caller=caller,
        outcome="ok" if outcome == "ok" else "error",
        error_class=type(error).__name__ if error is not None else None,
        latency_ms=int((perf_counter() - clock) * 1000),
    )
