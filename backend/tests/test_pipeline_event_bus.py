"""
Tests for `backend.app.orchestrator.event_bus.PipelineEventBus`.

The project carries no `pytest-asyncio`, so each test drives its scenario
through `asyncio.run(...)` around a coroutine helper — no plugin, no new
dependency. Coverage: buffered delivery, subscribe-first delivery, the terminal
sentinel ending iteration, teardown after the grace period, thread-safe publish
from a worker thread, full-queue drop-without-raise, and the constructor guards.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.app.orchestrator.event_bus import PipelineEventBus
from backend.app.orchestrator.models import (
    AgentStartedEvent,
    PipelineCompletedEvent,
    PipelineStartedEvent,
)


def _started(cid: UUID) -> PipelineStartedEvent:
    return PipelineStartedEvent(
        correlation_id=cid, timestamp=datetime.now(UTC), claim_id=uuid4()
    )


def _agent_started(cid: UUID) -> AgentStartedEvent:
    return AgentStartedEvent(
        correlation_id=cid, timestamp=datetime.now(UTC), agent="doc_parser"
    )


def _completed(cid: UUID) -> PipelineCompletedEvent:
    return PipelineCompletedEvent(
        correlation_id=cid, timestamp=datetime.now(UTC), status="settled"
    )


async def _drain(bus: PipelineEventBus, cid: UUID) -> list[str]:
    return [event.event_type async for event in bus.subscribe(cid)]


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #


def test_buffered_events_drained_in_order() -> None:
    """Publish before any subscriber; the subscriber still drains everything."""

    async def scenario() -> list[str]:
        bus = PipelineEventBus(grace_period_s=0.01, queue_maxsize=100)
        cid = uuid4()
        bus.publish(cid, _started(cid))
        bus.publish(cid, _agent_started(cid))
        bus.publish(cid, _completed(cid))
        return await _drain(bus, cid)

    assert asyncio.run(scenario()) == [
        "pipeline_started",
        "agent_started",
        "pipeline_completed",
    ]


def test_subscribe_first_then_publish() -> None:
    """A subscriber attached before the run receives events as they arrive."""

    async def scenario() -> list[str]:
        bus = PipelineEventBus(grace_period_s=0.01, queue_maxsize=100)
        cid = uuid4()

        async def produce() -> None:
            await asyncio.sleep(0.01)
            bus.publish(cid, _started(cid))
            bus.publish(cid, _completed(cid))

        received: list[str] = []

        async def consume() -> None:
            async for event in bus.subscribe(cid):
                received.append(event.event_type)

        await asyncio.gather(consume(), produce())
        return received

    assert asyncio.run(scenario()) == ["pipeline_started", "pipeline_completed"]


def test_terminal_event_ends_iteration() -> None:
    """Iteration stops at the terminal event even though more could be enqueued."""

    async def scenario() -> int:
        bus = PipelineEventBus(grace_period_s=0.01, queue_maxsize=100)
        cid = uuid4()
        bus.publish(cid, _completed(cid))
        # Anything enqueued after the terminal sentinel is never yielded.
        bus.publish(cid, _started(cid))
        return len(await _drain(bus, cid))

    # Only the terminal event is consumed before iteration returns.
    assert asyncio.run(scenario()) == 1


def test_queue_torn_down_after_grace() -> None:
    """The per-correlation queue is reaped after the grace period."""

    async def scenario() -> bool:
        bus = PipelineEventBus(grace_period_s=0.0, queue_maxsize=10)
        cid = uuid4()
        bus.publish(cid, _started(cid))
        bus.publish(cid, _completed(cid))
        await _drain(bus, cid)
        # Let the grace-period call_later fire.
        await asyncio.sleep(0.02)
        return cid in bus._queues

    assert asyncio.run(scenario()) is False


def test_thread_safe_publish_from_worker_thread() -> None:
    """`publish_threadsafe` from another thread reaches the subscriber."""

    async def scenario() -> list[str]:
        bus = PipelineEventBus(grace_period_s=0.01, queue_maxsize=100)
        cid = uuid4()
        loop = asyncio.get_running_loop()

        def worker() -> None:
            bus.publish_threadsafe(loop, cid, _started(cid))
            bus.publish_threadsafe(loop, cid, _completed(cid))

        received: list[str] = []

        async def consume() -> None:
            async for event in bus.subscribe(cid):
                received.append(event.event_type)

        consumer_task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)  # let the subscriber attach
        thread = threading.Thread(target=worker)
        thread.start()
        await consumer_task
        thread.join()
        return received

    assert asyncio.run(scenario()) == ["pipeline_started", "pipeline_completed"]


def test_full_queue_drops_without_raising() -> None:
    """A full queue drops the overflow event rather than raising into the run."""

    async def scenario() -> bool:
        bus = PipelineEventBus(grace_period_s=0.01, queue_maxsize=1)
        cid = uuid4()
        bus.publish(cid, _started(cid))  # fills the maxsize-1 queue
        bus.publish(cid, _agent_started(cid))  # dropped, must not raise
        return True

    assert asyncio.run(scenario()) is True


# --------------------------------------------------------------------------- #
# Constructor guards
# --------------------------------------------------------------------------- #


def test_negative_grace_period_raises() -> None:
    with pytest.raises(ValueError) as exc:
        PipelineEventBus(grace_period_s=-1.0, queue_maxsize=10)
    assert "grace_period_s must be >= 0" in str(exc.value)


def test_zero_queue_maxsize_raises() -> None:
    with pytest.raises(ValueError) as exc:
        PipelineEventBus(grace_period_s=1.0, queue_maxsize=0)
    assert "queue_maxsize must be >= 1" in str(exc.value)
