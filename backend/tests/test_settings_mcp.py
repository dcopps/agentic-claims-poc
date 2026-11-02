"""The `mcp` settings block: defaults, the environment path, and the blank-token rule."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from backend.settings import MCPSettings, Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.mcp.shared_token is None
    assert settings.mcp.token_label == "shared-token"
    assert settings.mcp.activity_replay_count == 20


def test_token_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP__SHARED_TOKEN", "abc")
    monkeypatch.setenv("MCP__TOKEN_LABEL", "demo-laptop")
    settings = Settings()
    assert settings.mcp.shared_token is not None
    assert settings.mcp.shared_token.get_secret_value() == "abc"
    assert settings.mcp.token_label == "demo-laptop"
    # SecretStr never prints its value.
    assert "abc" not in repr(settings.mcp)


def test_blank_token_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP__SHARED_TOKEN", "   ")
    assert Settings().mcp.shared_token is None
    assert MCPSettings(shared_token=SecretStr("")).shared_token is None


def test_bounds() -> None:
    with pytest.raises(ValidationError):
        MCPSettings(activity_replay_count=501)
    with pytest.raises(ValidationError):
        MCPSettings(token_label="")
    with pytest.raises(ValidationError):
        MCPSettings(unknown="x")  # type: ignore[call-arg]
