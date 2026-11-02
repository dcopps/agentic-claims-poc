"""
In-process broadcast of tool-call records to the live activity feed.

Not the pipeline event bus. `PipelineEventBus` is one reader per correlation
id with a terminal sentinel and a teardown timer — the right shape for a run
that starts and ends. The activity feed is the opposite: any number of readers,
one endless stream, every reader sees every record. So each subscriber gets its
own queue, there is no terminal, and a subscriber's queue disappears the moment
it stops iterating.

Shares the pipeline bus's two disciplines: publish only from the event-loop
thread (the recorder already runs there), and never raise into the publisher
— a full queue means a stuck reader, so the record is dropped for that reader
with a warning and every other reader still gets it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from backend.app.mcp.models import ToolCallRecord

_logger = logging.getLogger(__name__)


class ActivityBus:
    """Fan every published record out to every current subscriber."""

    def __init__(self, *, queue_maxsize: int) -> None:
        # The API passes a settings-derived value, but the bus owns its
        # boundary and re-checks rather than trusting the caller.
        if queue_maxsize < 1:
            raise ValueError(f"ActivityBus: queue_maxsize must be >= 1; got {queue_maxsize}")
        self._queue_maxsize = queue_maxsize
        self._queues: set[asyncio.Queue[ToolCallRecord]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    def publish(self, record: ToolCallRecord) -> None:
        """Offer `record` to every subscriber. Event-loop thread only."""
        for queue in list(self._queues):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                _logger.warning(
                    "ActivityBus: a subscriber's queue is full; dropping call_id=%s for it",
                    record.call_id,
                )

    async def subscribe(self) -> AsyncIterator[ToolCallRecord]:
        """Yield every record published from now on, until the consumer stops."""
        queue: asyncio.Queue[ToolCallRecord] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            # Runs when the consumer breaks out, the connection drops, or the
            # generator is closed — the queue must not outlive its reader.
            self._queues.discard(queue)
