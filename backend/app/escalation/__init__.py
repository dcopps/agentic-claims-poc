"""
Escalation policy engine.

Public surface:

  - `EscalationPolicy` — loads `policy.yaml` once at startup and evaluates it
    against a `PipelineState` with OR semantics.
  - `PolicyDocument` — the validated YAML shape.
  - `PipelineState` — the typed snapshot the engine evaluates.
  - `EscalationDecision` / `FiredRule` — the engine's verdict and its parts.

The policy file (`policy.yaml`) is the single source of truth for the rule set.
"""

from backend.app.escalation.models import (
    EscalationDecision,
    FiredRule,
    PipelineState,
    RuleType,
)
from backend.app.escalation.policy import EscalationPolicy, PolicyDocument

__all__ = [
    "EscalationDecision",
    "EscalationPolicy",
    "FiredRule",
    "PipelineState",
    "PolicyDocument",
    "RuleType",
]
