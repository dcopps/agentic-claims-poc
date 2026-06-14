"""
In-process pub/sub for pipeline progress events.

One `asyncio.Queue` per `correlation_id`. The orchestrator publishes events as
each step completes; an SSE handler subscribes and yields them to the client.
This is a deliberate prototype simplification — Phase 5 may replace it with a
real broker (Azure Service Bus in production). The SSE endpoint's coupling to
in-process subscribers is acceptable precisely because the prototype runs in one
process.

Design choices, each load-bearing:

  - **Buffered, not dropped.** The queue is created on the first publish *or*
    the first subscribe, whichever comes first. A subscriber that attaches after
    the run has started still drains the events buffered before it arrived — so
    the demo's "open the stream, then trigger the run" flow never races.
  - **Terminal-driven teardown.** Publishing a `pipeline_completed` /
    `pipeline_aborted` event enqueues a sentinel that ends the subscriber's
    iteration, then schedules the queue's removal after a short grace period so
    a late subscriber within that window still sees the whole run. The grace
    timer fires whether or not anyone subscribed, so queues never accumulate.
  - **Thread-safe publish.** The orchestrator runs in a worker thread (the API
    offloads its blocking I/O via `run_in_threadpool`). `publish_threadsafe`
    hops back onto the event loop before touching the queue, because
    `asyncio.Queue` is not safe to mutate from another thread.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from backend.app.orchestrator.models import (
    PipelineAbortedEvent,
    PipelineCompletedEvent,
    PipelineEvent,
)

_logger = logging.getLogger(__name__)


class _Terminal:
    """Sentinel enqueued after a terminal event to end a subscriber's loop."""


_TERMINAL = _Terminal()

# Items flowing through a queue are either a real event or the terminal sentinel.
_QueueItem = PipelineEvent | _Terminal


class PipelineEventBus:
    """Keyed in-memory event fan-out for pipeline runs."""

    def __init__(self, *, grace_period_s: float, queue_maxsize: int) -> None:
        # Defensive: the API passes settings-derived values, but the bus owns
        # the boundary, so it re-checks rather than trusting the caller.
        if grace_period_s < 0:
            raise ValueError(
                f"PipelineEventBus: grace_period_s must be >= 0; got {grace_period_s}"
            )
        if queue_maxsize < 1:
            raise ValueError(
                f"PipelineEventBus: queue_maxsize must be >= 1; got {queue_maxsize}"
            )
        self._grace_period_s = grace_period_s
        self._queue_maxsize = queue_maxsize
        self._queues: dict[UUID, asyncio.Queue[_QueueItem]] = {}

    def publish(self, correlation_id: UUID, event: PipelineEvent) -> None:
        """
        Enqueue `event` for `correlation_id`. Must be called from the event-loop
        thread; worker threads use `publish_threadsafe`. A terminal event also
        enqueues the sentinel and schedules teardown.
        """
        queue = self._get_or_create(correlation_id)
        self._put(correlation_id, queue, event)
        if isinstance(event, PipelineCompletedEvent | PipelineAbortedEvent):
            self._put(correlation_id, queue, _TERMINAL)
            self._schedule_teardown(correlation_id)

    def publish_threadsafe(
        self, loop: asyncio.AbstractEventLoop, correlation_id: UUID, event: PipelineEvent
    ) -> None:
        """Publish from a worker thread by hopping onto `loop` first."""
        loop.call_soon_threadsafe(self.publish, correlation_id, event)

    async def subscribe(self, correlation_id: UUID) -> AsyncIterator[PipelineEvent]:
        """
        Yield events for `correlation_id` until the terminal sentinel arrives.

        Creating the queue on subscribe (if a publish has not already) means a
        subscriber that attaches before the run starts simply waits on an empty
        queue; one that attaches mid-run drains what was buffered.
        """
        queue = self._get_or_create(correlation_id)
        while True:
            item = await queue.get()
            if isinstance(item, _Terminal):
                return
            yield item

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _get_or_create(self, correlation_id: UUID) -> asyncio.Queue[_QueueItem]:
        queue = self._queues.get(correlation_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._queue_maxsize)
            self._queues[correlation_id] = queue
        return queue

    def _put(
        self,
        correlation_id: UUID,
        queue: asyncio.Queue[_QueueItem],
        item: _QueueItem,
    ) -> None:
        # A full queue means a pathological run (thousands of events) or a stuck
        # subscriber. Drop and log rather than raising into the orchestrator —
        # losing a progress event must never fail the pipeline itself.
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            _logger.warning(
                "PipelineEventBus: queue full for correlation_id=%s; dropping an event",
                correlation_id,
            )

    def _schedule_teardown(self, correlation_id: UUID) -> None:
        """Remove the queue `grace_period_s` after its terminal event."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (a synchronous test publishing directly). The
            # caller can drop the queue itself; nothing to schedule.
            return
        loop.call_later(self._grace_period_s, self._queues.pop, correlation_id, None)
