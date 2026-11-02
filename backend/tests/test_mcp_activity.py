"""`ActivityBus`: broadcast to every subscriber, drop on a full queue, clean up."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import pytest

from backend.app.mcp.activity import ActivityBus
from backend.app.mcp.models import ToolCallRecord


def _record(call_id: int) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        called_at=datetime.now(UTC),
        tool="list_claims",
        arguments={},
        target=None,
        caller="shared-token",
        outcome="ok",
        error_class=None,
        latency_ms=1,
    )


async def _take(bus: ActivityBus, count: int) -> list[int]:
    seen: list[int] = []
    async for record in bus.subscribe():
        assert record.call_id is not None
        seen.append(record.call_id)
        if len(seen) == count:
            break
    return seen


def test_two_subscribers_both_receive_every_record() -> None:
    async def scenario() -> tuple[list[int], list[int], int]:
        bus = ActivityBus(queue_maxsize=10)
        first = asyncio.create_task(_take(bus, 2))
        second = asyncio.create_task(_take(bus, 2))
        await asyncio.sleep(0)  # let both subscribe before publishing
        assert bus.subscriber_count == 2
        bus.publish(_record(1))
        bus.publish(_record(2))
        a, b = await asyncio.gather(first, second)
        await asyncio.sleep(0)
        return a, b, bus.subscriber_count

    a, b, remaining = asyncio.run(scenario())
    assert a == [1, 2] and b == [1, 2]
    assert remaining == 0  # queues are removed when their readers stop


def test_full_queue_drops_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> list[int]:
        bus = ActivityBus(queue_maxsize=1)
        reader = asyncio.create_task(_take(bus, 1))
        await asyncio.sleep(0)
        with caplog.at_level(logging.WARNING):
            bus.publish(_record(1))
            bus.publish(_record(2))  # the reader has not drained yet: dropped for it
        return await reader

    assert asyncio.run(scenario()) == [1]
    assert "queue is full" in caplog.text


def test_publish_with_no_subscribers_is_a_no_op() -> None:
    bus = ActivityBus(queue_maxsize=5)
    bus.publish(_record(1))
    assert bus.subscriber_count == 0


def test_constructor_guard() -> None:
    with pytest.raises(ValueError, match="queue_maxsize must be >= 1; got 0"):
        ActivityBus(queue_maxsize=0)
