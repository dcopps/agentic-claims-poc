"""
MistralProvider — concrete `LLMProvider` for the Mistral SDK.

Mistral's SDK takes both the system and user content as message
entries (no top-level `system` parameter); the wrapper rearranges the
interface contract internally so the call site stays consistent with
Anthropic's. Mistral's JSON mode is native via
`response_format={"type": "json_object"}` and is used by the Validator
agent.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from mistralai.client import Mistral
from mistralai.client.errors import SDKError
from mistralai.client.models.chatcompletionresponse import (
    ChatCompletionResponse,
)
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


class MistralProvider(LLMProvider):
    """Wraps `mistralai.client.Mistral` behind the `LLMProvider` interface."""

    vendor: str = "mistral"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        api_logger: APILogger,
        pricing: dict[str, tuple[Decimal, Decimal]] | None = None,
    ) -> None:
        # Sanitise → validate → abort → execute. Identical defensive
        # ordering to the Anthropic provider; an empty key is never a
        # valid configuration.
        raw_key = api_key.get_secret_value().strip()
        if not raw_key:
            raise ValueError(
                "MistralProvider: api_key is empty — "
                "set MISTRAL_API_KEY before constructing the provider"
            )

        self._client = Mistral(api_key=raw_key)
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
                response_format=response_format,
                timeout_s=timeout_s,
            )
            response = self._coerce_response(sdk_response, t0)
            return response
        except SDKError as exc:
            captured_error = exc
            raise LLMProviderError(
                f"MistralProvider: {type(exc).__name__}: {exc}"
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
        response_format: ResponseFormat,
        timeout_s: float,
    ) -> ChatCompletionResponse:
        # Mistral's API expects the system message as the first
        # message in the list, not as a top-level parameter. The
        # wrapper does the translation so callers see a uniform
        # `system=...` argument.
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # SDK takes timeout in milliseconds.
            "timeout_ms": int(timeout_s * 1000),
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        sdk_response = self._client.chat.complete(**kwargs)
        if sdk_response is None:
            # Defence-in-depth — the SDK's typed signature doesn't
            # advertise Optional, but a hypothetical SDK regression
            # should not silently propagate None.
            raise LLMProviderError(
                "MistralProvider: chat.complete returned None"
            )
        return sdk_response

    def _coerce_response(
        self, sdk_response: ChatCompletionResponse, t0: float
    ) -> ProviderResponse:
        text = _extract_text(sdk_response)
        usage = sdk_response.usage
        prompt_tokens = int(usage.prompt_tokens or 0)
        completion_tokens = int(usage.completion_tokens or 0)
        total_tokens = int(usage.total_tokens or (prompt_tokens + completion_tokens))
        return ProviderResponse(
            text=text,
            model=sdk_response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
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
            provider="mistral",
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
        raise ValueError("MistralProvider.complete: system prompt is empty")
    if not user.strip():
        raise ValueError("MistralProvider.complete: user prompt is empty")
    if not model.strip():
        raise ValueError("MistralProvider.complete: model identifier is empty")


def _extract_text(sdk_response: ChatCompletionResponse) -> str:
    """
    Pull the assistant text out of a Mistral chat completion response.

    Refuses any shape that does not yield a non-empty string content —
    a tool-call response with `content=None` masquerading as a text
    completion would otherwise produce empty `ProviderResponse.text`.
    """
    choices = sdk_response.choices or []
    if not choices:
        raise LLMProviderError(
            "MistralProvider: response has no choices — "
            f"id={sdk_response.id!r}"
        )
    message = choices[0].message
    if message is None:
        raise LLMProviderError(
            "MistralProvider: first choice has no message — "
            f"id={sdk_response.id!r}"
        )
    content = message.content
    if not isinstance(content, str) or not content.strip():
        raise LLMProviderError(
            "MistralProvider: first choice content is not a non-empty "
            f"string; got type={type(content).__name__!r}, id={sdk_response.id!r}"
        )
    return content


def _safe_raw(sdk_response: ChatCompletionResponse) -> dict[str, Any]:
    """Convert the Mistral response to a plain dict for the audit log."""
    try:
        return sdk_response.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — best-effort serialisation
        return {}
