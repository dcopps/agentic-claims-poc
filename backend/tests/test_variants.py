"""
Tests for the variant mechanism — registry, pure resolution, and the Validator
override application.

The registry/resolution tests are pure (no DB, no keys). `_build_validator` is
tested with a `MockProvider` + the `stub_embedder` fixture, so it asserts the
override is applied without paying the real embedder cold-load.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from backend.app.orchestrator.variant_factory import (
    _build_validator,
    resolve_validator_config,
)
from backend.app.orchestrator.variant_registry import (
    UnknownVariantError,
    VariantRegistry,
)
from backend.settings import Settings

from .conftest import MockProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIANTS_PATH = REPO_ROOT / "backend/app/orchestrator/variants.yaml"

_VALID_BODY = """
version: 1
variants:
  default:
    description: baseline
  v2_strict_validator:
    description: strict
    validator:
      prompt_template: "validator_strict.md"
"""


def _registry() -> VariantRegistry:
    return VariantRegistry.load_from_yaml(VARIANTS_PATH)


# --------------------------------------------------------------------------- #
# Registry load + guards
# --------------------------------------------------------------------------- #


def test_load_real_variants_file() -> None:
    registry = _registry()
    assert registry.names() == [
        "default",
        "v2_haiku_validator",
        "v2_strict_validator",
    ]


def test_resolve_unknown_variant_raises() -> None:
    with pytest.raises(UnknownVariantError) as exc:
        _registry().resolve("v3_imaginary")
    assert "unknown variant" in str(exc.value)
    assert "v3_imaginary" in str(exc.value)


def test_load_missing_default_raises(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text(
        "version: 1\nvariants:\n  only_this:\n    description: x\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as exc:
        VariantRegistry.load_from_yaml(path)
    assert "must register a 'default' variant" in str(exc.value)


def test_load_malformed_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text("version: 1\nvariants: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        VariantRegistry.load_from_yaml(path)
    assert "not valid YAML" in str(exc.value)


def test_load_unknown_provider_raises(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text(
        _VALID_BODY
        + "  v2_bad:\n    description: bad\n    validator:\n      provider: openai\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        VariantRegistry.load_from_yaml(path)
    assert "schema validation" in str(exc.value)


def test_load_unknown_agent_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text(
        _VALID_BODY
        + "  v2_typo:\n    description: typo\n    validatr:\n      model: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        VariantRegistry.load_from_yaml(path)
    assert "schema validation" in str(exc.value)


# --------------------------------------------------------------------------- #
# Pure resolution
# --------------------------------------------------------------------------- #


def test_resolve_default_config() -> None:
    config = resolve_validator_config(_registry().resolve("default"))
    assert config.provider_name == "mistral"
    assert config.model is None
    assert config.user_template_name == "validator_template"


def test_resolve_strict_config_swaps_template() -> None:
    config = resolve_validator_config(_registry().resolve("v2_strict_validator"))
    assert config.user_template_name == "validator_strict"  # ".md" stripped
    assert config.provider_name == "mistral"
    assert config.model is None


def test_resolve_haiku_config_swaps_provider_and_model() -> None:
    config = resolve_validator_config(_registry().resolve("v2_haiku_validator"))
    assert config.provider_name == "anthropic"
    assert config.model == "claude-haiku-4-5-20251001"
    assert config.user_template_name == "validator_template"


# --------------------------------------------------------------------------- #
# Override application
# --------------------------------------------------------------------------- #


def test_build_validator_applies_template_override(
    db_settings: Settings, stub_embedder: Callable[[str], np.ndarray]
) -> None:
    config = resolve_validator_config(_registry().resolve("v2_strict_validator"))
    validator = _build_validator(
        config=config,
        settings=db_settings,
        provider=MockProvider(),
        embedder=stub_embedder,
    )
    assert validator._user_template_name == "validator_strict"


def test_build_validator_applies_model_override_without_mutating_settings(
    db_settings: Settings, stub_embedder: Callable[[str], np.ndarray]
) -> None:
    original_model = db_settings.llm.mistral.validator_model
    config = resolve_validator_config(_registry().resolve("v2_haiku_validator"))
    validator = _build_validator(
        config=config,
        settings=db_settings,
        provider=MockProvider(),
        embedder=stub_embedder,
    )
    # The override is local to the built agent...
    assert validator._settings.llm.mistral.validator_model == "claude-haiku-4-5-20251001"
    # ...and the shared Settings is untouched (deep copy).
    assert db_settings.llm.mistral.validator_model == original_model
