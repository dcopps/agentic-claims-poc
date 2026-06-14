"""
Pipeline orchestration.

Public surface:

  - `PipelineOrchestrator` — runs the four agents as one composed flow under a
    single correlation id and produces a typed `PipelineResult`.
  - `PipelineEventBus` — in-process pub/sub the SSE endpoint subscribes to.
  - `PipelineResult`, `PipelineStatus`, and the `PipelineEvent` family — the
    typed outcome and progress-event shapes Phases 5 and 6 consume.
"""

from backend.app.orchestrator.event_bus import PipelineEventBus
from backend.app.orchestrator.models import (
    AgentCompletedEvent,
    AgentStartedEvent,
    EscalationDecisionEvent,
    EventEmitter,
    PipelineAbortedEvent,
    PipelineCompletedEvent,
    PipelineEvent,
    PipelineResult,
    PipelineStartedEvent,
    PipelineStatus,
)
from backend.app.orchestrator.pipeline import PipelineOrchestrator

__all__ = [
    "AgentCompletedEvent",
    "AgentStartedEvent",
    "EscalationDecisionEvent",
    "EventEmitter",
    "PipelineAbortedEvent",
    "PipelineCompletedEvent",
    "PipelineEvent",
    "PipelineEventBus",
    "PipelineOrchestrator",
    "PipelineResult",
    "PipelineStartedEvent",
    "PipelineStatus",
]
