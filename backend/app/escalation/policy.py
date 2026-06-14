"""
Escalation policy engine.

The engine answers one question: after all four agents have run, must this claim
go to a human? It loads a declarative rule set from `policy.yaml` once at
startup and evaluates it against a `PipelineState` with OR semantics — any
single rule firing escalates, and every rule that fires is recorded.

Two layers, deliberately separated:

  - **Load** (`load_from_yaml`) — all I/O and all schema validation happen here,
    once, at startup. A malformed policy fails loudly at load, never silently at
    the first request. The YAML is validated through `PolicyDocument`, whose
    Literal-typed fields reject an unknown rule name, an unknown threshold field,
    or an unknown comparator at parse time — no hand-rolled allow-list needed.
  - **Evaluate** (`evaluate`) — a pure function on a typed input. No I/O, no
    clock, no randomness. Given the same state it returns the same decision,
    which is what makes it cheap to unit-test exhaustively.

Fail-closed posture: if evaluating any individual rule raises — for instance a
future caller hands in a `PipelineState` built via `model_construct` with a hole
in it — the engine records a synthetic fired rule and escalates, rather than
letting the exception abort the pipeline or, worse, letting a gap read as "no
rule fired" and auto-approve.
"""

from __future__ import annotations

import logging
import operator
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from backend.app.escalation.models import (
    EscalationDecision,
    FiredRule,
    PipelineState,
)

_logger = logging.getLogger(__name__)

# Maximum bytes we will read from the policy file. The real file is well under
# a kilobyte; the cap guards against the path being pointed at something huge.
_MAX_POLICY_BYTES = 64 * 1024

# The four recognised hard-rule names and the three recognised threshold fields.
# Expressed as Literals so the YAML schema validation rejects anything else at
# load — an unknown name is a configuration error, surfaced before the first
# request rather than swallowed at evaluation time.
_HardRuleName = Literal[
    "guardrail_failed",
    "claim_type_watchlist",
    "claimant_watchlist",
    "cross_jurisdictional",
]
_ThresholdField = Literal[
    "adjuster_settlement",
    "validator_confidence",
    "adjuster_confidence",
]
_Comparator = Literal[">", "<", ">=", "<="]

# Comparator symbol -> the operator applied as `operator(observed, threshold)`.
# Decimal is used on both sides so six-figure monetary comparisons are exact.
_COMPARATORS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}

# Threshold field name -> accessor extracting its value from the state as a
# Decimal. Confidence floats are routed through `str` first so the Decimal
# carries the exact decimal the model emitted, not a binary-float approximation.
_FIELD_ACCESSORS: dict[str, Callable[[PipelineState], Decimal]] = {
    "adjuster_settlement": lambda s: s.adjuster_output.recommended_settlement,
    "validator_confidence": lambda s: Decimal(str(s.validator_verdict.confidence)),
    "adjuster_confidence": lambda s: Decimal(str(s.adjuster_output.confidence)),
}


def _normalise(value: str) -> str:
    """Lower-case and strip so watchlist / marker matching is case-insensitive."""
    return value.strip().lower()


# --------------------------------------------------------------------------- #
# YAML schema (validated declaratively by Pydantic at load time)
# --------------------------------------------------------------------------- #


class _Watchlists(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_types: list[str] = []
    claimants: list[str] = []


class _HardRuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The Literal makes an unknown hard-rule name a load-time schema failure.
    name: _HardRuleName
    description: str


class _ThresholdRuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # Literals reject an unknown field or comparator at load; `value` as Decimal
    # rejects an unparseable boundary at load.
    field: _ThresholdField
    comparator: _Comparator
    value: Decimal
    description: str


class PolicyDocument(BaseModel):
    """The validated shape of `policy.yaml`. Locks at end of Phase 4."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    watchlists: _Watchlists
    cross_jurisdictional_markers: list[str]
    hard_rules: list[_HardRuleSpec]
    threshold_rules: list[_ThresholdRuleSpec]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


class EscalationPolicy:
    """Evaluates a loaded policy against a `PipelineState`."""

    def __init__(self, document: PolicyDocument) -> None:
        self._doc = document
        # Pre-normalise the watchlists and markers once so `evaluate` does no
        # string work beyond the per-claim comparison.
        self._claim_type_watch = frozenset(
            _normalise(x) for x in document.watchlists.claim_types
        )
        self._claimant_watch = frozenset(
            _normalise(x) for x in document.watchlists.claimants
        )
        self._markers = [_normalise(m) for m in document.cross_jurisdictional_markers]

    @classmethod
    def load_from_yaml(cls, path: Path) -> EscalationPolicy:
        """
        Load and validate the policy file. Sanitise -> validate -> abort ->
        execute: every failure raises `ValueError` with diagnostic context so a
        misconfigured policy is caught at startup, never at the first request.
        """
        resolved = path.expanduser().resolve()
        raw = _read_policy_text(resolved)
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"EscalationPolicy: policy file at {resolved} is not valid YAML; "
                f"error={exc} excerpt={raw[:500]!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                "EscalationPolicy: policy file must parse to a mapping; "
                f"got type={type(parsed).__name__} at {resolved}"
            )
        try:
            document = PolicyDocument.model_validate(parsed)
        except PydanticValidationError as exc:
            raise ValueError(
                "EscalationPolicy: policy file failed schema validation; "
                f"errors={exc.errors()} path={resolved}"
            ) from exc
        return cls(document)

    def evaluate(self, state: PipelineState) -> EscalationDecision:
        """
        Apply every rule to `state` and combine with OR semantics.

        Each rule is evaluated under a guard: a rule that raises (a holed state,
        a detector bug) escalates fail-closed rather than aborting the pipeline
        or being read as "did not fire". The fired list captures every rule that
        fired, in policy order.
        """
        fired: list[FiredRule] = []
        for hard in self._doc.hard_rules:
            fired.extend(self._eval_hard(hard, state))
        for threshold in self._doc.threshold_rules:
            fired.extend(self._eval_threshold(threshold, state))
        return EscalationDecision(
            escalate=len(fired) > 0,
            fired_rules=fired,
            reasoning=_compose_reasoning(fired),
        )

    # ------------------------------------------------------------------ #
    # Per-rule evaluation. Each returns a 0-or-1-element list so `evaluate`
    # can `extend` uniformly, and each fails closed on an unexpected error.
    # ------------------------------------------------------------------ #

    def _eval_hard(
        self, spec: _HardRuleSpec, state: PipelineState
    ) -> list[FiredRule]:
        try:
            if not self._detect_hard(spec.name, state):
                return []
            return [
                FiredRule(name=spec.name, rule_type="hard", description=spec.description)
            ]
        except Exception as exc:  # noqa: BLE001 — fail-closed is the whole point
            return [_fail_closed_rule(spec.name, "hard", spec.description, exc)]

    def _eval_threshold(
        self, spec: _ThresholdRuleSpec, state: PipelineState
    ) -> list[FiredRule]:
        try:
            observed = _FIELD_ACCESSORS[spec.field](state)
            if not _COMPARATORS[spec.comparator](observed, spec.value):
                return []
            return [
                FiredRule(
                    name=spec.name,
                    rule_type="threshold",
                    description=spec.description,
                    observed_value=str(observed),
                )
            ]
        except Exception as exc:  # noqa: BLE001 — fail-closed is the whole point
            return [_fail_closed_rule(spec.name, "threshold", spec.description, exc)]

    def _detect_hard(self, name: str, state: PipelineState) -> bool:
        """Dispatch a hard rule to its detector. Returns True iff it fires."""
        if name == "guardrail_failed":
            return not state.guardrail_output.passed
        if name == "claim_type_watchlist":
            return _normalise(state.doc_parser_output.claim_type) in self._claim_type_watch
        if name == "claimant_watchlist":
            claimant = _normalise(state.doc_parser_output.claimant_identifier)
            return claimant in self._claimant_watch
        if name == "cross_jurisdictional":
            jurisdiction = _normalise(state.doc_parser_output.jurisdiction)
            return any(marker in jurisdiction for marker in self._markers)
        # Unreachable: the Literal on `_HardRuleSpec.name` rejects unknown names
        # at load. Re-asserting here keeps the boundary honest if that changes.
        raise ValueError(f"EscalationPolicy: unrecognised hard rule name {name!r}")


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _read_policy_text(resolved: Path) -> str:
    """Read the policy file with existence / type / size guards."""
    if not resolved.exists():
        raise ValueError(f"EscalationPolicy: policy file not found at {resolved}")
    if not resolved.is_file():
        raise ValueError(
            f"EscalationPolicy: policy path is not a regular file: {resolved}"
        )
    size = resolved.stat().st_size
    if size > _MAX_POLICY_BYTES:
        raise ValueError(
            f"EscalationPolicy: policy file too large: {size} bytes at {resolved} "
            f"(cap is {_MAX_POLICY_BYTES} bytes — refusing to load)"
        )
    return resolved.read_text(encoding="utf-8")


def _fail_closed_rule(
    name: str, rule_type: str, description: str, exc: Exception
) -> FiredRule:
    """
    Build the synthetic fired rule for a rule that could not be evaluated.

    A gap reached at evaluation time (e.g. a state field that is None) escalates
    to a human — the safe direction — and the gap is logged so the operator can
    diagnose it. `rule_type` is narrowed back to the Literal by construction.
    """
    _logger.warning(
        "EscalationPolicy: rule %r could not be evaluated (%s: %s); failing closed",
        name,
        type(exc).__name__,
        exc,
    )
    narrowed: Literal["hard", "threshold"] = (
        "threshold" if rule_type == "threshold" else "hard"
    )
    reason = f"could not be evaluated ({type(exc).__name__}); failing closed"
    return FiredRule(
        name=name,
        rule_type=narrowed,
        description=f"{description} — {reason}",
    )


def _compose_reasoning(fired: list[FiredRule]) -> str:
    """Compose a deterministic, human-readable summary of the decision."""
    if not fired:
        return "No escalation rules fired; claim is eligible for auto-settlement."
    names = ", ".join(rule.name for rule in fired)
    return f"Escalation required: {len(fired)} rule(s) fired ({names})."
