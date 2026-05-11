"""
Tests for `backend.app.llm.mistral_provider.MistralProvider`.

The SDK client is replaced with a stub via `monkeypatch.setattr` so no
network traffic happens. Tests focus on the wrapper logic: constructor
guards, request shape (system message first, not a top-level param),
response coercion, error funneling, JSON-mode flag, and APILogger
integration.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from mistralai.client.errors import SDKError
from pydantic import SecretStr

from backend.app.llm.mistral_provider import MistralProvider
from backend.app.llm.provider import LLMProviderError
from backend.app.logging.api_logger import APILogger


def _fake_response(
    text: str = "{}",
    model: str = "mistral-large-2512",
    prompt_tokens: int = 100,
    completion_tokens: int = 30,
) -> SimpleNamespace:
    class FakeResponse(SimpleNamespace):
        def model_dump(self, mode: str = "python") -> dict[str, object]:
            del mode
            return {"id": "fake", "model": model}

    message = SimpleNamespace(content=text, role="assistant")
    choice = SimpleNamespace(message=message, finish_reason="stop", index=0)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return FakeResponse(
        id="fake-id",
        object="chat.completion",
        model=model,
        usage=usage,
        choices=[choice],
        created=1,
    )


def _logger(captured: list[str]) -> APILogger:
    return APILogger(enabled=True, excerpt_chars=500, sink=captured.append)


def test_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError) as exc_info:
        MistralProvider(
            api_key=SecretStr(""),
            api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
        )
    assert "MISTRAL_API_KEY" in str(exc_info.value)


def test_complete_places_system_message_first(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: list[dict[str, object]] = []
    captured_logs: list[str] = []

    def fake_complete(**kwargs: object) -> SimpleNamespace:
        captured_kwargs.append(kwargs)
        return _fake_response()

    provider = MistralProvider(
        api_key=SecretStr("sk"), api_logger=_logger(captured_logs)
    )
    monkeypatch.setattr(provider._client.chat, "complete", fake_complete)

    provider.complete(
        system="role",
        user="narrative",
        model="mistral-large-latest",
        max_tokens=256,
        temperature=0.1,
        correlation_id=uuid4(),
        agent="validator",
        step="coverage_check",
        response_format="json",
        timeout_s=30.0,
    )

    messages = captured_kwargs[0]["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": "role"}
    assert messages[1] == {"role": "user", "content": "narrative"}
    assert captured_kwargs[0]["response_format"] == {"type": "json_object"}
    # 30 seconds -> 30_000 ms
    assert captured_kwargs[0]["timeout_ms"] == 30_000
    assert len(captured_logs) == 1


def test_complete_translates_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_logs: list[str] = []
    import httpx

    fake_response = httpx.Response(429, content=b"{}")

    def fake_complete(**_kwargs: object) -> SimpleNamespace:
        raise SDKError("rate limited", raw_response=fake_response, body="{}")

    provider = MistralProvider(
        api_key=SecretStr("sk"), api_logger=_logger(captured_logs)
    )
    monkeypatch.setattr(provider._client.chat, "complete", fake_complete)

    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            system="s",
            user="u",
            model="mistral-large-latest",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )
    assert "SDKError" in str(exc_info.value)
    assert len(captured_logs) == 1
    assert '"error"' in captured_logs[0]


def test_empty_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = MistralProvider(
        api_key=SecretStr("sk"),
        api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
    )

    def fake_complete(**_kwargs: object) -> SimpleNamespace:
        resp = _fake_response()
        resp.choices[0].message.content = None
        return resp

    monkeypatch.setattr(provider._client.chat, "complete", fake_complete)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            system="s",
            user="u",
            model="mistral-large-latest",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )
    assert "non-empty" in str(exc_info.value)


def test_no_choices_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = MistralProvider(
        api_key=SecretStr("sk"),
        api_logger=APILogger(enabled=False, excerpt_chars=200, sink=lambda _l: None),
    )

    def fake_complete(**_kwargs: object) -> SimpleNamespace:
        resp = _fake_response()
        resp.choices = []
        return resp

    monkeypatch.setattr(provider._client.chat, "complete", fake_complete)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            system="s",
            user="u",
            model="mistral-large-latest",
            max_tokens=1,
            temperature=0.0,
            correlation_id=uuid4(),
            agent="validator",
            step="coverage_check",
        )
    assert "no choices" in str(exc_info.value)
