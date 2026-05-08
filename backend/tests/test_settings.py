"""Settings model tests.

Two responsibilities:
  1. Confirm `Settings()` instantiates with defaults — the model contract
     for callers that don't supply a YAML overlay or env vars.
  2. Trigger the YAML loader's malformed-file guard so we know the failure
     path is wired correctly. The guard is the only piece of defensive
     programming in the Phase 0 backend; if it stops working silently the
     settings hierarchy collapses into "defaults only" without warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.settings import Settings, _load_yaml_overrides


def test_settings_instantiates_with_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "agentic-claims-poc"
    assert settings.environment == "dev"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"
    assert settings.cors_allowed_origins == ["http://localhost:5173"]


def test_yaml_loader_returns_empty_when_file_absent(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    assert _load_yaml_overrides(missing) == {}


def test_yaml_loader_returns_empty_when_file_is_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert _load_yaml_overrides(empty) == {}


def test_yaml_loader_aborts_on_malformed_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    # Unclosed bracket — guaranteed YAMLError.
    bad.write_text("app_name: [unterminated\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        _load_yaml_overrides(bad)

    message = str(excinfo.value)
    # Path must appear so the operator can locate the offending file
    # without re-running anything.
    assert str(bad) in message
    # Underlying parser detail must appear so the cause is traceable.
    assert "not valid YAML" in message


def test_yaml_loader_aborts_on_non_mapping_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        _load_yaml_overrides(bad)

    assert "must parse to a mapping" in str(excinfo.value)


def test_yaml_loader_aborts_when_file_is_directory(tmp_path: Path) -> None:
    # tmp_path itself is a directory — a path that exists but isn't a file
    # must abort rather than silently fall through.
    with pytest.raises(ValueError) as excinfo:
        _load_yaml_overrides(tmp_path)

    assert "not a regular file" in str(excinfo.value)
