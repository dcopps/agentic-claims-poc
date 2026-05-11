"""
AnthropicProvider — concrete `LLMProvider` for the Anthropic SDK.

The wrapper hides three things from callers:

  - The SDK shape: Anthropic takes `system` as a top-level parameter
    and the user content as a `messages=[{"role":"user", ...}]` list.
  - The error funnel: every `anthropic.APIError` subclass is re-raised
    as `LLMProviderError` so call sites catch one type.
  - The audit / log side effect: every call produces one
    `APICallRecord` regardless of success or failure.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import anthropic
from pydantic import SecretStr

from backend.app.llm.provider import (
    LLMProvider,
    LLMProviderError,
    ProviderResponse,
    ResponseFormat,
)
from backend.app.logging.api_logger import (
    APIAgentName,
    APICallRecord,
    APILogger,
    coerce_error,
    compute_cost_usd,
    make_excerpt,
)


class AnthropicProvider(LLMProvider):
    """Wraps `anthropic.Anthropic` behind the `LLMProvider` interface."""

    vendor: str = "anthropic"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        api_logger: APILogger,
        pricing: dict[str, tuple[Decimal, Decimal]] | None = None,
    ) -> None:
        # Sanitise — strip an accidentally-quoted secret. Validate —
        # an empty key is never a valid configuration. Abort — raise
        # before instantiating the SDK client so misconfiguration
        # surfaces with a clean message instead of an opaque 401.
        raw_key = api_key.get_secret_value().strip()
        if not raw_key:
            raise ValueError(
                "AnthropicProvider: api_key is empty — "
                "set ANTHROPIC_API_KEY before constructing the provider"
            )

        self._client = anthropic.Anthropic(api_key=raw_key)
        self._api_logger: APILogger = api_logger
        self._pricing: dict[str, tuple[Decimal, Decimal]] = pricing or {}

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
        _validate_inputs(system=system, user=user, model=model)
        # `response_format` parameter is accepted for interface
        # symmetry with the Mistral provider. The Anthropic SDK has no
        # native JSON-only flag — the caller's system prompt must
        # enforce JSON when "json" is requested. Documented loudly
        # rather than warning at runtime so the cost is zero.
        del response_format
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()
        captured_error: BaseException | None = None
        response: ProviderResponse | None = None
        try:
            sdk_response = self._invoke_sdk(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )
            response = self._coerce_response(sdk_response, t0)
            return response
        except anthropic.APIError as exc:
            captured_error = exc
            raise LLMProviderError(
                f"AnthropicProvider: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            self._emit_record(
                correlation_id=correlation_id,
                agent=agent,
                step=step,
                model=model,
                system=system,
                user=user,
                response=response,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=captured_error,
            )

    def _invoke_sdk(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> anthropic.types.Message:
        # `system` lives at the top level, not inside `messages`. The
        # vendor's contract is what the wrapper hides from callers.
        return self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            timeout=timeout_s,
        )

    def _coerce_response(
        self, sdk_response: anthropic.types.Message, t0: float
    ) -> ProviderResponse:
        text = _extract_text(sdk_response)
        usage = sdk_response.usage
        prompt_tokens = int(usage.input_tokens)
        completion_tokens = int(usage.output_tokens)
        return ProviderResponse(
            text=text,
            model=sdk_response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw=_safe_raw(sdk_response),
        )

    def _emit_record(
        self,
        *,
        correlation_id: UUID,
        agent: APIAgentName,
        step: str,
        model: str,
        system: str,
        user: str,
        response: ProviderResponse | None,
        started_at: datetime,
        completed_at: datetime,
        latency_ms: int,
        error: BaseException | None,
    ) -> None:
        excerpt_budget = self._api_logger.excerpt_chars
        redactor = self._api_logger.redact
        prompt_tokens = response.prompt_tokens if response is not None else 0
        completion_tokens = response.completion_tokens if response is not None else 0
        total_tokens = response.total_tokens if response is not None else 0
        cost_usd = (
            compute_cost_usd(
                pricing=self._pricing,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            if response is not None
            else None
        )
        record = APICallRecord(
            correlation_id=correlation_id,
            agent=agent,
            step=step,
            provider="anthropic",
            model=model,
            system_prompt_excerpt=make_excerpt(system, excerpt_budget, redactor),
            user_prompt_excerpt=make_excerpt(user, excerpt_budget, redactor),
            response_excerpt=(
                make_excerpt(response.text, excerpt_budget, redactor)
                if response is not None
                else ""
            ),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            started_at=started_at,
            completed_at=completed_at,
            error=coerce_error(error) if error is not None else None,
        )
        self._api_logger.log_call(record)


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _validate_inputs(*, system: str, user: str, model: str) -> None:
    """Reject empty/whitespace prompts and model identifiers up-front."""
    if not system.strip():
        raise ValueError("AnthropicProvider.complete: system prompt is empty")
    if not user.strip():
        raise ValueError("AnthropicProvider.complete: user prompt is empty")
    if not model.strip():
        raise ValueError("AnthropicProvider.complete: model identifier is empty")


def _extract_text(sdk_response: anthropic.types.Message) -> str:
    """
    Defensively pull the text out of an Anthropic Message.

    The SDK returns `content` as a list of typed blocks. The validator
    contract is a single text response; we accept the first text block
    and refuse anything else loudly so a tool-call response cannot
    silently masquerade as a completion.
    """
    blocks = list(sdk_response.content)
    if not blocks:
        raise LLMProviderError(
            "AnthropicProvider: response.content is empty — "
            f"stop_reason={sdk_response.stop_reason!r}"
        )
    first = blocks[0]
    text = getattr(first, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise LLMProviderError(
            "AnthropicProvider: first content block is not text or is empty; "
            f"got type={type(first).__name__} stop_reason={sdk_response.stop_reason!r}"
        )
    return text


def _safe_raw(sdk_response: anthropic.types.Message) -> dict[str, Any]:
    """Convert the SDK response to a plain dict for the audit log."""
    # `model_dump(mode="json")` round-trips through pydantic's JSON
    # serializer so datetimes / UUIDs / enums all come out as
    # plain JSON-native types. The audit layer canonicaliser refuses
    # anything else.
    try:
        return sdk_response.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — best-effort serialisation
        # Last-ditch: return an empty dict rather than crashing the
        # caller. The text is already on `ProviderResponse.text`.
        return {}
