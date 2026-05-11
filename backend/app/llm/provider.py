"""
LLM Gateway interface.

Two design contracts that lock at end of Phase 2 and that Phases 3+
depend on:

  1. **`LLMProvider.complete(...)` accepts `system` and `user` as
     separate keyword-only arguments.** Providers translate to
     vendor-specific shapes internally. The interface itself encodes
     the project-wide system/user-separation rule — a call site cannot
     conflate them by accident.
  2. **`ProviderResponse` is the typed return.** Callers never see a
     raw SDK object. The shape includes the parsed text, the model
     identifier (as the SDK reports it back — useful when "latest"
     aliases resolve to a dated model), token counts, latency, and a
     `raw` dict for the audit log. Adding fields is non-breaking;
     renaming or removing requires explicit interface review.

Errors funnel through a single typed exception, `LLMProviderError`, so
call sites catch one type regardless of which SDK actually raised.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from backend.app.logging.api_logger import APIAgentName

# Pinned set of response shapes the Gateway recognises. `"text"` is a
# free-form completion; `"json"` requests JSON-only output if the
# underlying provider supports it (Mistral does via `response_format`;
# Anthropic does not have a native JSON mode and relies on prompt
# discipline to enforce the format).
ResponseFormat = Literal["text", "json"]


class LLMProviderError(RuntimeError):
    """
    Single error type every provider raises on a non-recoverable
    failure (auth, network, malformed SDK response, empty content).

    Inherits from `RuntimeError` so a top-level `except RuntimeError`
    in legacy callers does not silently catch it; callers should catch
    `LLMProviderError` explicitly. The original SDK exception is
    chained via `raise ... from exc` so a tracer can see the wire-side
    detail.
    """


@dataclass(frozen=True)
class ProviderResponse:
    """
    Typed result of a single `LLMProvider.complete(...)` call.

    `raw` carries the SDK's serialised response (model_dump form) so
    the audit log can store it without round-tripping through json
    serialisation a second time. Treat `raw` as opaque from outside
    the provider module — its shape varies by vendor.
    """

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base for the two concrete provider implementations."""

    # `vendor` is a class attribute so the factory and the APILogger
    # can identify the provider without isinstance() chains. The
    # concrete subclasses override it.
    vendor: str = "unknown"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
        correlation_id: UUID,
        agent: APIAgentName,
        step: str,
        response_format: ResponseFormat = "text",
        timeout_s: float = 60.0,
    ) -> ProviderResponse:
        """
        Run a single completion.

        Keyword-only. `system` and `user` are separate strings —
        providers translate to their SDK's preferred shape internally.

        `correlation_id`, `agent`, and `step` are required metadata
        the implementation pipes into the APILogger's record. Every
        LLM call in this codebase originates from an agent step, so
        these are part of the contract rather than optional sidecar
        data.

        Raises `LLMProviderError` on any non-recoverable failure.
        Never returns a partially-populated response.
        """
        raise NotImplementedError
