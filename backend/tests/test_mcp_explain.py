"""
`compose_explanation` over the fixture rows — pure, no database.

The fixture is the Harborline run `0cdfa114` the plan uses as its worked
example, so the first test is that example: the refused claim beside the
code's reason, the claim settled on the rules alone, every section tagged
with its row. The others vary the rows to hit each composition rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from backend.app.audit.repository import AuditEntry
from backend.app.audit.verify import AuditBreak, ChainVerification
from backend.app.mcp.explain import agent_rows, compose_explanation, strip_prompts
from backend.tests.mcp_fixture import (
    FIXTURE_DISCARDED_QUOTE,
    fixture_claim,
    fixture_entries,
    load_fixture,
)

_OK = ChainVerification(ok=True, rows_checked=118, first_break=None)


def _compose(entries: list[AuditEntry]) -> object:
    return compose_explanation(uuid4(), fixture_claim(), entries, _OK)


def _without(step: str, entries: list[AuditEntry]) -> list[AuditEntry]:
    return [entry for entry in entries if entry.step != step]


def _with_payload(entry: AuditEntry, **changes: object) -> AuditEntry:
    return entry.model_copy(update={"payload": {**entry.payload, **changes}})


def test_worked_example_harborline() -> None:
    cid = load_fixture()["correlation_id"]
    explanation = compose_explanation(cid, fixture_claim(), fixture_entries(), _OK)

    assert explanation.outcome.status == "settled"
    assert explanation.outcome.settlement == "82500.00"
    assert explanation.outcome.fired_rule_names == []
    assert explanation.outcome.source is not None and explanation.outcome.source.audit_id == 76

    assert explanation.coverage is not None
    assert explanation.coverage.covered is True
    assert explanation.coverage.confidence == 0.92
    assert [p.section for p in explanation.coverage.passages_seen] == [
        "Named Perils Covered",
        "Exclusions",
        "Sub-Limits",
    ]
    assert [p.section for p in explanation.coverage.passages_cited] == [
        "Named Perils Covered",
        "Exclusions",
    ]
    assert explanation.coverage.source.audit_id == 72

    assert explanation.settlement is not None
    assert explanation.settlement.recommended == "82500.00"
    assert explanation.settlement.range is not None
    assert (explanation.settlement.range.floor, explanation.settlement.range.ceiling) == (
        "50000",
        "200000",
    )
    assert explanation.settlement.demo_fixture is False
    assert FIXTURE_DISCARDED_QUOTE in explanation.settlement.reasoning

    guardrail = explanation.guardrail
    assert guardrail is not None
    assert guardrail.passed is True
    assert guardrail.rule_engine_flags == []
    assert guardrail.llm_flags_counted == []
    assert [flag.quote for flag in guardrail.llm_flags_discarded] == [FIXTURE_DISCARDED_QUOTE]
    assert guardrail.llm_flags_discarded[0].reason == "quote_not_a_provision"
    assert guardrail.llm_verification_recorded is True
    assert guardrail.source.audit_id == 74

    assert explanation.escalation is not None
    assert explanation.escalation.escalate is False
    assert explanation.escalation.reconstructed is False
    assert explanation.escalation.source.audit_id == 75

    assert explanation.human_decision is None
    assert [(m.agent, m.provider) for m in explanation.models] == [
        ("doc_parser", "anthropic"),
        ("validator", "anthropic"),
        ("adjuster", "anthropic"),
        ("guardrail", "anthropic"),
    ]
    assert all(
        m.model == m.requested_model == "claude-haiku-4-5-20251001" for m in explanation.models
    )
    assert explanation.chain.scope == "whole_ledger"
    assert explanation.chain.rows_checked == 118
    assert explanation.chain.run_rows == 7
    assert explanation.started_at is not None and explanation.completed_at is not None


def test_every_source_matches_its_row() -> None:
    entries = fixture_entries()
    explanation = compose_explanation(uuid4(), fixture_claim(), entries, _OK)
    by_id = {entry.audit_id: entry for entry in entries}
    sections = [
        explanation.coverage,
        explanation.settlement,
        explanation.guardrail,
        explanation.escalation,
        explanation.outcome,
        *explanation.models,
    ]
    for section in sections:
        assert section is not None and section.source is not None
        row = by_id[section.source.audit_id]
        assert (section.source.step, section.source.chain_hash) == (row.step, row.chain_hash)


def test_in_flight_run_has_running_outcome_and_no_completed_at() -> None:
    entries = _without("pipeline_settled", fixture_entries())
    explanation = compose_explanation(uuid4(), fixture_claim(), entries, _OK)
    assert explanation.outcome.status == "running"
    assert explanation.outcome.source is None
    assert explanation.completed_at is None


def test_aborted_run_has_null_sections() -> None:
    entries = fixture_entries()[:3]  # started, doc_extract, coverage_check
    aborted = entries[0].model_copy(
        update={
            "audit_id": 999,
            "step": "pipeline_aborted",
            "payload": {
                "status": "aborted",
                "failing_agent": "adjuster",
                "error_type": "ProviderError",
                "error_message": "boom",
                "completed_at": datetime.now(UTC).isoformat(),
            },
        }
    )
    explanation = compose_explanation(uuid4(), fixture_claim(), [*entries, aborted], _OK)
    assert explanation.outcome.status == "aborted"
    assert explanation.outcome.failing_agent == "adjuster"
    assert explanation.outcome.error_type == "ProviderError"
    assert explanation.settlement is None
    assert explanation.guardrail is None
    assert explanation.escalation is None
    assert explanation.coverage is not None


def test_guardrail_throw_reconstructs_the_escalation() -> None:
    entries = _without("escalation_decision", _without("pipeline_settled", fixture_entries()))
    terminal = entries[0].model_copy(
        update={
            "audit_id": 998,
            "step": "pipeline_awaiting_human",
            "payload": {
                "status": "awaiting_human",
                "escalate": True,
                "fired_rule_names": ["guardrail_failed"],
                "reason": "guardrail_threw",
                "error_type": "RuntimeError",
                "error_message": "x",
                "completed_at": datetime.now(UTC).isoformat(),
            },
        }
    )
    explanation = compose_explanation(uuid4(), fixture_claim(), [*entries, terminal], _OK)
    assert explanation.escalation is not None
    assert explanation.escalation.reconstructed is True
    assert [rule.name for rule in explanation.escalation.fired_rules] == ["guardrail_failed"]
    assert explanation.escalation.source.audit_id == 998


def test_pre_0912_guardrail_row_reports_verification_not_recorded() -> None:
    entries = fixture_entries()
    guardrail = next(e for e in entries if e.step == "output_check")
    payload = {k: v for k, v in guardrail.payload.items() if not k.startswith("llm_flags_")}
    older = [
        guardrail.model_copy(update={"payload": payload}) if e is guardrail else e for e in entries
    ]
    explanation = compose_explanation(uuid4(), fixture_claim(), older, _OK)
    assert explanation.guardrail is not None
    assert explanation.guardrail.llm_verification_recorded is False
    assert explanation.guardrail.llm_flags_discarded == []


def test_human_decision_row_is_reported() -> None:
    entries = fixture_entries()
    human = entries[0].model_copy(
        update={
            "audit_id": 997,
            "agent": "human",
            "step": "human_approval",
            "payload": {
                "decision": "approved",
                "decided_by": "A. Reviewer",
                "comment": "fine",
                "decided_at": "2026-10-31T10:00:00+00:00",
            },
        }
    )
    explanation = compose_explanation(uuid4(), fixture_claim(), [*entries, human], _OK)
    assert explanation.human_decision is not None
    assert explanation.human_decision.decision == "approved"
    assert explanation.human_decision.decided_by == "A. Reviewer"
    assert explanation.human_decision.source.audit_id == 997


def test_demo_fixture_adjuster_appears_without_a_model() -> None:
    entries = fixture_entries()
    adjuster = next(e for e in entries if e.step == "settlement_estimate")
    fixture_row = _with_payload(
        adjuster,
        demo_fixture=True,
        llm_call={"provider": "demo_fixture", "note": "no model call", "latency_ms": 0},
    )
    swapped = [fixture_row if e is adjuster else e for e in entries]
    explanation = compose_explanation(uuid4(), fixture_claim(), swapped, _OK)
    assert explanation.settlement is not None and explanation.settlement.demo_fixture is True
    adjuster_use = next(m for m in explanation.models if m.agent == "adjuster")
    assert (adjuster_use.provider, adjuster_use.model) == ("demo_fixture", None)


def test_chain_break_is_carried_through() -> None:
    broken = ChainVerification(
        ok=False,
        rows_checked=3,
        first_break=AuditBreak(audit_id=2, kind="row_hash_mismatch", expected="a", actual="b"),
    )
    explanation = compose_explanation(uuid4(), fixture_claim(), fixture_entries(), broken)
    assert explanation.chain.ok is False
    assert explanation.chain.first_break is not None
    assert explanation.chain.first_break.audit_id == 2


def test_empty_rows_are_refused() -> None:
    with pytest.raises(ValueError, match="has no audit rows"):
        compose_explanation(uuid4(), fixture_claim(), [], _OK)


def test_agent_rows_report_recorded_latency() -> None:
    rows = agent_rows(fixture_entries())
    assert [row.agent for row in rows] == ["doc_parser", "validator", "adjuster", "guardrail"]
    assert [row.model_latency_ms for row in rows] == [1184, 3144, 2418, 1701]
    assert all(row.demo_fixture is False for row in rows)


def test_strip_prompts_removes_only_the_prompt_and_copies() -> None:
    payload: dict[str, Any] = {
        "llm_call": {"provider": "anthropic", "prompt": {"system": "s", "user": "u"}},
        "x": 1,
    }
    stripped = strip_prompts(payload)
    assert stripped == {"llm_call": {"provider": "anthropic"}, "x": 1}
    assert "prompt" in payload["llm_call"]  # the original is untouched
    assert strip_prompts({"no_call": True}) == {"no_call": True}
