"""
Tests for `backend.app.escalation.policy.EscalationPolicy`.

The engine is a pure function on a typed input, so these tests need no database
and no LLM — they build a `PipelineState`, evaluate, and assert on the decision.
Load-path tests write throwaway policy files under `tmp_path`.

Coverage: each hard rule fires; each threshold rule fires at the correct
boundary; OR-combination captures every rule; the dropped " and " marker no
longer false-positives; the fail-closed guard escalates a holed state; and every
load guard surfaces a useful `ValueError`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail_models import GuardrailFlag, GuardrailOutput
from backend.app.agents.validator_models import CitedChunk, ValidatorVerdict
from backend.app.escalation.models import PipelineState
from backend.app.escalation.policy import EscalationPolicy, PolicyDocument

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "backend/app/escalation/policy.yaml"


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _state(
    *,
    claim_type: str = "water_damage",
    jurisdiction: str = "United Kingdom",
    claimant: str = "Harborline Logistics Ltd",
    settlement: str = "85000.00",
    validator_confidence: float = 0.9,
    adjuster_confidence: float = 0.9,
    guardrail_passed: bool = True,
) -> PipelineState:
    """Build a valid `PipelineState`, overridable per rule under test."""
    flags = (
        []
        if guardrail_passed
        else [GuardrailFlag(kind="pii", detail="example", source="rule")]
    )
    return PipelineState(
        claim_id=uuid4(),
        correlation_id=uuid4(),
        doc_parser_output=DocParserOutput(
            loss_date=date(2026, 4, 18),
            jurisdiction=jurisdiction,
            claim_type=claim_type,
            claimed_amount=Decimal("85000.00"),
            claimant_identifier=claimant,
            narrative_summary="Burst supply line flooded the warehouse mezzanine.",
        ),
        validator_verdict=ValidatorVerdict(
            covered=True,
            confidence=validator_confidence,
            reasoning="Sudden and accidental water discharge is covered.",
            policy_basis="Section 4 — Water Damage.",
            cited_chunks=[CitedChunk(chunk_id=uuid4(), section="Section 4")],
        ),
        adjuster_output=AdjusterOutput(
            recommended_settlement=Decimal(settlement),
            confidence=adjuster_confidence,
            reasoning="Settlement sits within the market range for the loss.",
        ),
        guardrail_output=GuardrailOutput(
            passed=guardrail_passed,
            flags=flags,
            summary="No issues found." if guardrail_passed else "Issues found.",
        ),
    )


def _policy(
    *,
    claim_types: list[str] | None = None,
    claimants: list[str] | None = None,
    markers: list[str] | None = None,
) -> EscalationPolicy:
    """Build an in-memory policy with the locked rules; watchlists overridable."""
    document = PolicyDocument.model_validate(
        {
            "version": 1,
            "watchlists": {
                "claim_types": claim_types or [],
                "claimants": claimants or [],
            },
            "cross_jurisdictional_markers": (
                markers if markers is not None else ["/", "multi-jurisdiction", "cross-border"]
            ),
            "hard_rules": [
                {"name": "guardrail_failed", "description": "Guardrail did not pass"},
                {"name": "claim_type_watchlist", "description": "Claim type watchlisted"},
                {"name": "claimant_watchlist", "description": "Claimant watchlisted"},
                {"name": "cross_jurisdictional", "description": "Spans jurisdictions"},
            ],
            "threshold_rules": [
                {
                    "name": "settlement_over_ceiling",
                    "field": "adjuster_settlement",
                    "comparator": ">",
                    "value": "250000",
                    "description": "settlement > $250,000",
                },
                {
                    "name": "validator_confidence_floor",
                    "field": "validator_confidence",
                    "comparator": "<",
                    "value": "0.65",
                    "description": "validator confidence < 0.65",
                },
                {
                    "name": "adjuster_confidence_floor",
                    "field": "adjuster_confidence",
                    "comparator": "<",
                    "value": "0.75",
                    "description": "adjuster confidence < 0.75",
                },
            ],
        }
    )
    return EscalationPolicy(document)


def _fired_names(policy: EscalationPolicy, state: PipelineState) -> set[str]:
    return {rule.name for rule in policy.evaluate(state).fired_rules}


# --------------------------------------------------------------------------- #
# No rules fire
# --------------------------------------------------------------------------- #


def test_clean_claim_does_not_escalate() -> None:
    decision = _policy().evaluate(_state())
    assert decision.escalate is False
    assert decision.fired_rules == []
    assert "auto-settlement" in decision.reasoning


# --------------------------------------------------------------------------- #
# Hard rules
# --------------------------------------------------------------------------- #


def test_guardrail_failed_fires() -> None:
    decision = _policy().evaluate(_state(guardrail_passed=False))
    assert decision.escalate is True
    fired = {r.name: r for r in decision.fired_rules}
    assert "guardrail_failed" in fired
    assert fired["guardrail_failed"].rule_type == "hard"
    # Hard rules carry no observed value.
    assert fired["guardrail_failed"].observed_value is None


def test_claim_type_watchlist_fires_case_insensitive() -> None:
    policy = _policy(claim_types=["FIRE"])
    assert _fired_names(policy, _state(claim_type="fire")) == {"claim_type_watchlist"}


def test_claimant_watchlist_fires_case_insensitive() -> None:
    policy = _policy(claimants=["sanctioned entity ltd"])
    fired = _fired_names(policy, _state(claimant="Sanctioned Entity Ltd"))
    assert fired == {"claimant_watchlist"}


def test_cross_jurisdictional_fires_on_slash_marker() -> None:
    fired = _fired_names(_policy(), _state(jurisdiction="Bermuda / United Kingdom"))
    assert fired == {"cross_jurisdictional"}


def test_cross_jurisdictional_does_not_false_positive_on_and() -> None:
    # Regression for the dropped " and " marker: real single jurisdictions
    # contain "and" and must not escalate.
    for jurisdiction in ("Trinidad and Tobago", "Antigua and Barbuda"):
        assert _policy().evaluate(_state(jurisdiction=jurisdiction)).escalate is False


# --------------------------------------------------------------------------- #
# Threshold rules — boundary behaviour
# --------------------------------------------------------------------------- #


def test_settlement_threshold_strict_at_ceiling() -> None:
    # Exactly 250000 does NOT fire (comparator is strict >); a cent over does.
    assert _policy().evaluate(_state(settlement="250000.00")).escalate is False
    fired = _fired_names(_policy(), _state(settlement="250000.01"))
    assert "settlement_over_ceiling" in fired


def test_settlement_threshold_records_observed_value() -> None:
    decision = _policy().evaluate(_state(settlement="850000.00"))
    rule = next(r for r in decision.fired_rules if r.name == "settlement_over_ceiling")
    assert rule.rule_type == "threshold"
    assert rule.observed_value == "850000.00"


def test_validator_confidence_floor_boundary() -> None:
    assert _policy().evaluate(_state(validator_confidence=0.65)).escalate is False
    fired = _fired_names(_policy(), _state(validator_confidence=0.64))
    assert "validator_confidence_floor" in fired


def test_adjuster_confidence_floor_boundary() -> None:
    assert _policy().evaluate(_state(adjuster_confidence=0.75)).escalate is False
    fired = _fired_names(_policy(), _state(adjuster_confidence=0.74))
    assert "adjuster_confidence_floor" in fired


# --------------------------------------------------------------------------- #
# OR-combination
# --------------------------------------------------------------------------- #


def test_or_semantics_capture_every_fired_rule() -> None:
    policy = _policy(claim_types=["fire"])
    state = _state(
        claim_type="fire",
        settlement="900000.00",
        adjuster_confidence=0.5,
        guardrail_passed=False,
    )
    decision = policy.evaluate(state)
    assert decision.escalate is True
    assert {r.name for r in decision.fired_rules} == {
        "guardrail_failed",
        "claim_type_watchlist",
        "settlement_over_ceiling",
        "adjuster_confidence_floor",
    }
    assert "4 rule(s) fired" in decision.reasoning


# --------------------------------------------------------------------------- #
# Fail-closed guard
# --------------------------------------------------------------------------- #


def test_holed_state_fails_closed() -> None:
    # A future caller builds a partial state via model_construct (no validation),
    # leaving adjuster_output as None. The threshold accessor raises; the engine
    # must escalate fail-closed rather than crash or silently pass.
    good = _state()
    holed = PipelineState.model_construct(
        claim_id=good.claim_id,
        correlation_id=good.correlation_id,
        doc_parser_output=good.doc_parser_output,
        validator_verdict=good.validator_verdict,
        adjuster_output=None,
        guardrail_output=good.guardrail_output,
    )
    decision = _policy().evaluate(holed)
    assert decision.escalate is True
    # The synthetic fired rule names the rule that could not be evaluated.
    assert any(
        "failing closed" in r.description for r in decision.fired_rules
    )


# --------------------------------------------------------------------------- #
# Load path — the real file
# --------------------------------------------------------------------------- #


def test_load_real_policy_file() -> None:
    policy = EscalationPolicy.load_from_yaml(POLICY_PATH)
    # The shipped file does not escalate the clean demo claim.
    assert policy.evaluate(_state()).escalate is False
    # ...and does escalate an $850k fire loss on the settlement ceiling.
    fired = _fired_names(policy, _state(settlement="850000.00"))
    assert "settlement_over_ceiling" in fired


# --------------------------------------------------------------------------- #
# Load guards
# --------------------------------------------------------------------------- #


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(tmp_path / "nope.yaml")
    assert "not found" in str(exc.value)


def test_load_non_mapping_raises(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "must parse to a mapping" in str(exc.value)


def _write_policy(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


_VALID_BODY = """
version: 1
watchlists:
  claim_types: []
  claimants: []
cross_jurisdictional_markers: ["/"]
hard_rules:
  - name: guardrail_failed
    description: d
threshold_rules:
  - name: settlement_over_ceiling
    field: adjuster_settlement
    comparator: ">"
    value: "250000"
    description: d
"""


def test_load_bad_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    _write_policy(path, _VALID_BODY.replace("version: 1", "version: 2"))
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "schema validation" in str(exc.value)


def test_load_unknown_hard_rule_name_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    _write_policy(path, _VALID_BODY.replace("guardrail_failed", "guardrail_exploded"))
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "schema validation" in str(exc.value)
    assert "guardrail_exploded" in str(exc.value)


def test_load_unknown_threshold_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    _write_policy(path, _VALID_BODY.replace("adjuster_settlement", "made_up_field"))
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "schema validation" in str(exc.value)


def test_load_bad_comparator_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    _write_policy(path, _VALID_BODY.replace('comparator: ">"', 'comparator: "=="'))
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "schema validation" in str(exc.value)


def test_load_unparseable_value_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    _write_policy(path, _VALID_BODY.replace('value: "250000"', 'value: "not-a-number"'))
    with pytest.raises(ValueError) as exc:
        EscalationPolicy.load_from_yaml(path)
    assert "schema validation" in str(exc.value)
