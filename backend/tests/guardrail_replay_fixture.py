"""
Replay-fixture contract for the Guardrail regression test (Phase 9.2.1).

One file describes one recorded Guardrail run, reduced to the four values the
`guardrail_template` user prompt takes, plus enough provenance to trace the file
back to its audit row. The writer is `scripts/extract-guardrail-replay-fixture.py`
and the reader is `test_guardrail_replay.py`; keeping the contract in one module
means a fixture the script would not write is a fixture the test will not load.

The `inputs` block deliberately holds template *values*, not the recorded full
prompt, so the test is forced through the current system prompt and template.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ExpectedVerdict = Literal["pass", "flag_hallucinated_citation"]


class ReplayInputs(BaseModel):
    """The four `guardrail_template` placeholder values, exactly as recorded."""

    model_config = ConfigDict(extra="forbid")

    adjuster_settlement: str = Field(min_length=1)
    adjuster_reasoning: str = Field(min_length=1)
    retrieved_chunks: str = Field(min_length=1)
    rule_flags_already_found: str = Field(min_length=1)


class RecordedOutcome(BaseModel):
    """What the Guardrail decided on the day. Provenance, never a test input."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    rule_flags: list[dict[str, Any]]
    llm_flags: list[dict[str, Any]]


class ReplayFixture(BaseModel):
    """A recorded Guardrail run and the verdict the current prompt must reach on it."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    label: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    recorded_at: datetime
    source: str = Field(min_length=1)
    expected: ExpectedVerdict
    recorded_outcome: RecordedOutcome
    # Hash of the system prompt that was in force when the run was recorded. The
    # test does not use it: the point of the replay is the *current* prompt.
    recorded_system_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs: ReplayInputs


def load_replay_fixture(path: Path) -> ReplayFixture:
    """
    Read and validate one fixture file; every failure names the file and the cause.

    Unreadable, non-JSON and contract-violating files all raise `ValueError` rather
    than yielding a partial fixture, because a silently skipped fixture would turn
    the pre-demo check into a false pass.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Replay fixture {path}: cannot read file: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Replay fixture {path}: not valid JSON: {exc}") from exc
    try:
        return ReplayFixture.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"Replay fixture {path}: does not match the fixture contract: {exc}"
        ) from exc
