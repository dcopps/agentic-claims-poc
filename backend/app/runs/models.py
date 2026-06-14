"""
Typed shapes for the runs domain.

A "run" is one execution of the pipeline, identified by its correlation_id and
reconstructed entirely from the audit_log. These shapes are what the runs and
comparison APIs return:

  - `RunStatus` — a run's lifecycle outcome. `running` covers a run with a
    `pipeline_started` entry but no terminal entry yet.
  - `RunSummary` — the one-line view of a run, for the per-claim runs list.
  - `DiffSummary` — the fields where two runs differ (settlement, escalation,
    fired rules, guardrail) — the comparison's headline.
  - `RunComparison` — two reconstructed `PipelineResult`s plus their diff.

They lock at end of Phase 5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.orchestrator.models import PipelineResult

RunStatus = Literal["running", "settled", "awaiting_human", "aborted"]


class RunSummary(BaseModel):
    """One-line summary of a past (or in-flight) run, for the per-claim list."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    variant: str
    status: RunStatus
    started_at: datetime
    # None while the run is still in flight (no terminal entry yet).
    completed_at: datetime | None
    # None when escalation was never decided (aborted, or still running).
    escalate: bool | None


class DiffSummary(BaseModel):
    """The fields where two runs differ. Reasoning prose is intentionally excluded."""

    model_config = ConfigDict(extra="forbid")

    settlement_changed: bool
    settlement_a: str | None
    settlement_b: str | None
    escalation_changed: bool
    escalate_a: bool | None
    escalate_b: bool | None
    # Rule names present in B but not A (added) / in A but not B (removed).
    fired_rules_added: list[str]
    fired_rules_removed: list[str]
    guardrail_changed: bool
    guardrail_passed_a: bool | None
    guardrail_passed_b: bool | None


class RunComparison(BaseModel):
    """Two reconstructed runs of the same claim, side by side, plus their diff."""

    model_config = ConfigDict(extra="forbid")

    run_a: PipelineResult
    run_b: PipelineResult
    diff: DiffSummary
