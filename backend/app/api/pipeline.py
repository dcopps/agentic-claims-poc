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
from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from backend.app.orchestrator import (
    PipelineEventBus,
    PipelineOrchestrator,
    PipelineResult,
)
from backend.app.orchestrator.models import EventEmitter, PipelineEvent
from backend.app.orchestrator.variant_factory import build_variant_orchestrator
from backend.app.orchestrator.variant_registry import (
    UnknownVariantError,
    VariantRegistry,
)
from backend.app.runs import RunsRepository
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


def get_variant_registry(request: Request) -> VariantRegistry:
    registry: VariantRegistry = request.app.state.variant_registry
    return registry


# A factory that produces an orchestrator for a given variant name. Routing all
# orchestrator construction through one factory gives the tests a single override
# point and lets `run` and `replay` share the default/variant logic.
OrchestratorFactory = Callable[[str], PipelineOrchestrator]


def get_orchestrator_factory(request: Request) -> OrchestratorFactory:
    """
    Return a factory `make(variant) -> PipelineOrchestrator`.

    The `default` variant resolves the lazily-built, cached default orchestrator
    (the build wires the real agent graph and loads the embedder, too heavy for
    every startup). A non-default variant is built fresh per run — variant agents
    are not cached.
    """
    app = request.app

    def make(variant: str) -> PipelineOrchestrator:
        if variant == "default":
            orchestrator: PipelineOrchestrator | None = getattr(
                app.state, "orchestrator", None
            )
            if orchestrator is None:
                orchestrator = PipelineOrchestrator.with_defaults(
                    app.state.settings, policy=app.state.policy
                )
                app.state.orchestrator = orchestrator
            return orchestrator
        return build_variant_orchestrator(
            app.state.settings, app.state.policy, app.state.variant_registry, variant
        )

    return make


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@pipeline_router.post("/run/{claim_id}", response_model=PipelineResult)
async def run_pipeline(
    claim_id: UUID,
    variant: str = "default",
    correlation_id: UUID | None = None,
    factory: OrchestratorFactory = Depends(get_orchestrator_factory),
    registry: VariantRegistry = Depends(get_variant_registry),
    bus: PipelineEventBus = Depends(get_event_bus),
    settings: Settings = Depends(get_settings),
) -> PipelineResult:
    """Run the pipeline for `claim_id` (optionally under a variant)."""
    await _require_known_claim(settings, claim_id)
    _require_known_variant(registry, variant)
    await _reject_if_active(settings, claim_id)
    return await _execute(factory(variant), claim_id, correlation_id, variant, bus)


@pipeline_router.post("/replay/{claim_id}", response_model=PipelineResult)
async def replay_pipeline(
    claim_id: UUID,
    variant: str = "v2_strict_validator",
    correlation_id: UUID | None = None,
    factory: OrchestratorFactory = Depends(get_orchestrator_factory),
    registry: VariantRegistry = Depends(get_variant_registry),
    bus: PipelineEventBus = Depends(get_event_bus),
    settings: Settings = Depends(get_settings),
) -> PipelineResult:
    """
    Re-process a claim under a variant.

    Unlike `run`, replay requires a prior completed run (409 if none — nothing to
    replay) and mints a fresh correlation_id so the prior run is never
    overwritten; both runs sit side-by-side in the audit vault.
    """
    await _require_known_claim(settings, claim_id)
    _require_known_variant(registry, variant)
    await _require_prior_terminal_run(settings, claim_id)
    await _reject_if_active(settings, claim_id)
    return await _execute(factory(variant), claim_id, correlation_id, variant, bus)


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


async def _execute(
    orchestrator: PipelineOrchestrator,
    claim_id: UUID,
    correlation_id: UUID | None,
    variant: str,
    bus: PipelineEventBus,
) -> PipelineResult:
    """Run the orchestrator in a worker thread, bridging its events to the bus."""
    cid = correlation_id or uuid4()
    emit = _make_emitter(bus, cid)
    result: PipelineResult = await run_in_threadpool(
        orchestrator.run, claim_id, correlation_id=cid, emit=emit, variant=variant
    )
    return result


def _require_known_variant(registry: VariantRegistry, variant: str) -> None:
    """404 if the variant is not registered — checked before any agent is built."""
    try:
        registry.resolve(variant)
    except UnknownVariantError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _reject_if_active(settings: Settings, claim_id: UUID) -> None:
    """409 if a run is already in flight for the claim (single-writer per claim)."""
    if await run_in_threadpool(_is_run_active, settings, claim_id):
        raise HTTPException(
            status_code=409,
            detail=f"a run is already in flight for claim {claim_id}",
        )


async def _require_prior_terminal_run(settings: Settings, claim_id: UUID) -> None:
    """409 if the claim has no completed run to replay."""
    if not await run_in_threadpool(_has_terminal_run, settings, claim_id):
        raise HTTPException(
            status_code=409,
            detail=f"nothing to replay: claim {claim_id} has no completed run",
        )


def _is_run_active(settings: Settings, claim_id: UUID) -> bool:
    with open_connection(settings) as conn:
        return RunsRepository.is_run_active(conn, claim_id)


def _has_terminal_run(settings: Settings, claim_id: UUID) -> bool:
    with open_connection(settings) as conn:
        summaries = RunsRepository.list_runs_for_claim(conn, claim_id)
    return any(summary.status != "running" for summary in summaries)


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
