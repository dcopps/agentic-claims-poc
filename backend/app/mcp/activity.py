"""
In-process broadcast of tool-call records to the live activity feed.

Not the pipeline event bus. `PipelineEventBus` is one reader per correlation
id with a terminal sentinel and a teardown timer — the right shape for a run
that starts and ends. The activity feed is the opposite: any number of readers,
one endless stream, every reader sees every record. So each subscriber gets its
own queue, there is no terminal, and a subscriber's queue disappears when the
subscription closes.

**Subscription is eager.** `subscribe()` registers the queue the moment it is
called, not when iteration starts, so the feed endpoint can subscribe, then
read the replay rows from the table, and be certain that a record written in
between is already waiting in its queue rather than lost. The subscription is
an async context manager so the queue is removed on every exit path.

Shares the pipeline bus's two disciplines: publish only from the event-loop
thread (the recorder already runs there), and never raise into the publisher
— a full queue means a stuck reader, so the record is dropped for that reader
with a warning and every other reader still gets it.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType

from backend.app.mcp.models import ToolCallRecord

_logger = logging.getLogger(__name__)


class Subscription:
    """One reader's queue: an async iterator that must be closed, hence a context manager.

    Registration happened in `ActivityBus.subscribe`; closing needs no await,
    so the context manager is synchronous and works inside an async generator."""

    def __init__(self, bus: ActivityBus, queue: asyncio.Queue[ToolCallRecord]) -> None:
        self._bus = bus
        self._queue = queue

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> ToolCallRecord:
        return await self._queue.get()

    def __enter__(self) -> Subscription:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._bus._remove(self._queue)


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

    def subscribe(self) -> Subscription:
        """Register a reader now; it receives every record published from this point."""
        queue: asyncio.Queue[ToolCallRecord] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues.add(queue)
        return Subscription(self, queue)

    def _remove(self, queue: asyncio.Queue[ToolCallRecord]) -> None:
        self._queues.discard(queue)
