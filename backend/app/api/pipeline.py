"""
Pipeline API — the synchronous trigger and the SSE progress stream.

Two endpoints, deliberately split:

  - `POST /api/pipeline/run/{claim_id}` runs the whole pipeline and returns the
    typed `PipelineResult`. It accepts an optional `correlation_id` so a client
    can open the stream *first*, then trigger the run with the same id — the flow
    the Phase 6 frontend uses to watch a run live.
  - `GET /api/pipeline/stream/{correlation_id}` is the SSE side: it subscribes to
    the in-process event bus for that correlation id and yields each progress
    event as it is published.

The orchestrator is plain and synchronous (blocking psycopg + LLM I/O), so the
run endpoint offloads it to a worker thread via `run_in_threadpool` and bridges
its `emit` callback back onto the event loop with the bus's thread-safe publish.
All asyncio lives here, at the edge; the orchestrator never sees it.

Status-code policy: a run that ends `settled`, `awaiting_human`, or `aborted`
(an agent failed mid-run) is a successful *pipeline outcome* and returns 200 with
the typed body. Only request-level failures use 4xx — an unknown claim id is a
pre-flight 404 (so a bad request never writes a started/aborted audit pair), and
a malformed path UUID is FastAPI's automatic 422.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from backend.app.escalation import EscalationPolicy
from backend.app.orchestrator import (
    PipelineEventBus,
    PipelineOrchestrator,
    PipelineResult,
)
from backend.app.orchestrator.models import EventEmitter, PipelineEvent
from backend.db.connection import open_connection
from backend.settings import Settings

_logger = logging.getLogger(__name__)

pipeline_router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# --------------------------------------------------------------------------- #
# Dependencies — resolve the lifespan-built collaborators from app state.
# --------------------------------------------------------------------------- #


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_event_bus(request: Request) -> PipelineEventBus:
    bus: PipelineEventBus = request.app.state.event_bus
    return bus


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    """
    Return the app's orchestrator, building it lazily on first use.

    The build wires the real agent graph, which loads the embedder — too heavy
    to pay at every startup (it would slow health probes and CI). Deferring to
    first pipeline request keeps startup cheap; the result is cached on app
    state so subsequent requests reuse it.
    """
    app = request.app
    orchestrator: PipelineOrchestrator | None = getattr(app.state, "orchestrator", None)
    if orchestrator is None:
        policy: EscalationPolicy = app.state.policy
        orchestrator = PipelineOrchestrator.with_defaults(app.state.settings, policy=policy)
        app.state.orchestrator = orchestrator
    return orchestrator


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@pipeline_router.post("/run/{claim_id}", response_model=PipelineResult)
async def run_pipeline(
    claim_id: UUID,
    correlation_id: UUID | None = None,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
    bus: PipelineEventBus = Depends(get_event_bus),
    settings: Settings = Depends(get_settings),
) -> PipelineResult:
    """Run the pipeline for `claim_id` and return the typed outcome."""
    await _require_known_claim(settings, claim_id)
    cid = correlation_id or uuid4()
    emit = _make_emitter(bus, cid)
    # Offload the blocking orchestrator to a worker thread so the event loop
    # stays free to serve the concurrent SSE stream for this correlation id.
    result: PipelineResult = await run_in_threadpool(
        orchestrator.run, claim_id, correlation_id=cid, emit=emit
    )
    return result


@pipeline_router.get("/stream/{correlation_id}")
async def stream_pipeline(
    correlation_id: UUID,
    bus: PipelineEventBus = Depends(get_event_bus),
) -> EventSourceResponse:
    """Stream pipeline progress events for `correlation_id` as Server-Sent Events."""

    async def event_source() -> AsyncIterator[dict[str, str]]:
        async for event in bus.subscribe(correlation_id):
            # `event:` is the typed event name; `data:` is the event JSON. The
            # frontend dispatches on the event name (Phase 6).
            yield {"event": event.event_type, "data": event.model_dump_json()}

    return EventSourceResponse(event_source())


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_emitter(bus: PipelineEventBus, correlation_id: UUID) -> EventEmitter:
    """
    Build the orchestrator's `emit` callback.

    The orchestrator runs in a worker thread, so the callback must hop back onto
    the event loop before touching the bus's asyncio queue — the loop is captured
    here while it is running.
    """
    loop = asyncio.get_running_loop()

    def emit(event: PipelineEvent) -> None:
        bus.publish_threadsafe(loop, correlation_id, event)

    return emit


async def _require_known_claim(settings: Settings, claim_id: UUID) -> None:
    """404 if the claim is not in the claims table — a pre-flight bad-request guard."""
    exists = await run_in_threadpool(_claim_exists, settings, claim_id)
    if not exists:
        raise HTTPException(status_code=404, detail=f"claim not found: {claim_id}")


def _claim_exists(settings: Settings, claim_id: UUID) -> bool:
    conn: psycopg.Connection
    with open_connection(settings) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM claims WHERE claim_id = %s", (claim_id,))
        return cur.fetchone() is not None
