"""
Agents — single-responsibility actors in the claims pipeline.

Phase 2 contributed the Validator. Phase 3 adds Doc-Parser, Adjuster,
and Guardrail. Each agent is a small class with one entry method
(`evaluate(...)`), its collaborators injected through the constructor
so the unit test surface is a stub-swap rather than a monkeypatch.

The agents do not share a base class — Phase 3's plan rejected that
abstraction. Shared mechanical helpers live in `_shared.py`.
"""

from backend.app.agents.adjuster import Adjuster
from backend.app.agents.adjuster_models import AdjusterOutput, AdjusterResult
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.doc_parser_models import (
    DocParserOutput,
    DocParserResult,
)
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.guardrail_models import (
    GuardrailFlag,
    GuardrailFlagKind,
    GuardrailFlagSource,
    GuardrailOutput,
    GuardrailResult,
)
from backend.app.agents.guardrail_rules import GuardrailRuleEngine
from backend.app.agents.validator import Validator
from backend.app.agents.validator_models import (
    CitedChunk,
    RetrievedChunk,
    ValidatorResult,
    ValidatorVerdict,
)

__all__ = [
    "Adjuster",
    "AdjusterOutput",
    "AdjusterResult",
    "CitedChunk",
    "DocParser",
    "DocParserOutput",
    "DocParserResult",
    "Guardrail",
    "GuardrailFlag",
    "GuardrailFlagKind",
    "GuardrailFlagSource",
    "GuardrailOutput",
    "GuardrailResult",
    "GuardrailRuleEngine",
    "RetrievedChunk",
    "Validator",
    "ValidatorResult",
    "ValidatorVerdict",
]
