"""
Tests for `backend.app.llm.anthropic_provider.AnthropicProvider`.

The SDK client is replaced with a stub via `unittest.mock.patch.object`
so no network traffic happens. The tests focus on the wrapper logic:
constructor guards, request shape, response coercion, error funneling,
and APILogger integration.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import anthropic
import pytest
from pydantic import SecretStr

from backend.app.llm.anthropic_provider import AnthropicProvider
from backend.app.llm.provider import LLMProviderError
from backend.app.logging.api_logger import APILogger


def _fake_message(
    text: str = "ok", model: str = "claude-x", input_tokens: int = 10, output_tokens: int = 5
) -> SimpleNamespace:
    """Build a SimpleNamespace mimicking the anthropic.types.Message shape."""

    class FakeMessage(SimpleNamespace):
        def model_dump(self, mode: str = "python") -> dict[str, object]:
            del mode
            return {"model": model, "text": text}

    return FakeMessage(
        content=[SimpleNamespace(text=text, type="text")],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
        stop_reason="end_turn",
    )


def _logger(captured: list[str]) -> APILogger:
    return APILogger(enabled=True, excerpt_chars=500, sink=captured.append)


def test_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError) as exc_info:
        AnthropicProvider(
            api_key=SecretStr("   "),
            api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
        )
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_complete_returns_typed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_calls: list[dict[str, object]] = []
    captured_logs: list[str] = []

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured_calls.append(kwargs)
        return _fake_message()

    provider = AnthropicProvider(
        api_key=SecretStr("sk-test"), api_logger=_logger(captured_logs)
    )
    monkeypatch.setattr(provider._client.messages, "create", fake_create)

    response = provider.complete(
        system="role text",
        user="claim narrative",
        model="claude-x",
        max_tokens=256,
        temperature=0.0,
        correlation_id=uuid4(),
        agent="validator",
        step="coverage_check",
    )

    # SDK call shape: system at top level, user content in messages list.
    assert captured_calls[0]["system"] == "role text"
    assert captured_calls[0]["messages"] == [
        {"role": "user", "content": "claim narrative"}
    ]
    assert captured_calls[0]["model"] == "claude-x"
    assert response.text == "ok"
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 5
    assert response.total_tokens == 15
    # APILogger emitted one success record.
    assert len(captured_logs) == 1


def test_complete_translates_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_logs: list[str] = []
    import httpx

    fake_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def fake_create(**_kwargs: object) -> SimpleNamespace:
        # Real APIError requires a httpx.Request — passing a SimpleNamespace
        # would be a type-system fib that mypy catches.
        raise anthropic.APIError(message="boom", request=fake_request, body=None)

    provider = AnthropicProvider(
        api_key=SecretStr("sk-test"), api_logger=_logger(captured_logs)
    )
    monkeypatch.setattr(provider._client.messages, "create", fake_create)

    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            system="s",
            user="u",
            model="claude-x",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )
    assert "APIError" in str(exc_info.value)
    # APILogger emitted one failure record.
    assert len(captured_logs) == 1
    assert '"error"' in captured_logs[0]


def test_complete_rejects_empty_system(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AnthropicProvider(
        api_key=SecretStr("sk-test"),
        api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
    )

    def boom(**_kwargs: object) -> SimpleNamespace:
        raise AssertionError("SDK should not be called when validation fails")

    monkeypatch.setattr(provider._client.messages, "create", boom)
    with pytest.raises(ValueError):
        provider.complete(
            system="",
            user="u",
            model="claude-x",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )


def test_empty_response_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AnthropicProvider(
        api_key=SecretStr("sk-test"),
        api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
    )

    def fake_create(**_kwargs: object) -> SimpleNamespace:
        empty = _fake_message()
        empty.content = []
        return empty

    monkeypatch.setattr(provider._client.messages, "create", fake_create)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            system="s",
            user="u",
            model="claude-x",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )
    assert "content is empty" in str(exc_info.value)
