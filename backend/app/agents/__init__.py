"""
Agents — single-responsibility actors in the claims pipeline.

Phase 2 contributes only the Validator. Phase 3 adds Doc-Parser,
Adjuster, and Guardrail. Each agent is a small class with one entry
method, its collaborators injected through the constructor so the unit
test surface is a stub-swap rather than a monkeypatch.
"""

from backend.app.agents.validator import Validator
from backend.app.agents.validator_models import (
    CitedChunk,
    RetrievedChunk,
    ValidatorResult,
    ValidatorVerdict,
)

__all__ = [
    "CitedChunk",
    "RetrievedChunk",
    "Validator",
    "ValidatorResult",
    "ValidatorVerdict",
]
