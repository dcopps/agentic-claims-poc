"""
Tests for the variant mechanism — registry, pure settings resolution, and the
override application.

The registry/resolution tests are pure (no DB, no keys). `_build_validator` is
tested with a `MockProvider` + the `stub_embedder` fixture, so it asserts the
override is applied without paying the real embedder cold-load. Provider wiring
through the real factory lives in `test_agent_wiring.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from backend.app.orchestrator.variant_factory import (
    _build_validator,
    _set_model,
    _set_provider,
    resolve_validator_template,
    resolve_variant_settings,
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
        "v1_mistral",
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


def test_load_prompt_template_under_adjuster_raises(tmp_path: Path) -> None:
    # The Adjuster has no user-template hook; accepting the key would silently
    # ignore it, so the schema must refuse it at load.
    path = tmp_path / "v.yaml"
    path.write_text(
        _VALID_BODY
        + "  v2_bad:\n    description: bad\n    adjuster:\n"
        + "      prompt_template: adjuster_strict.md\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        VariantRegistry.load_from_yaml(path)
    assert "schema validation" in str(exc.value)
    assert "prompt_template" in str(exc.value)


# --------------------------------------------------------------------------- #
# Pure resolution
# --------------------------------------------------------------------------- #


def test_resolve_default_keeps_all_anthropic(db_settings: Settings) -> None:
    spec = _registry().resolve("default")
    cfg = resolve_variant_settings(db_settings, spec)
    for agent in ("doc_parser", "validator", "adjuster", "guardrail"):
        assert cfg.llm.provider_for(agent) == "anthropic"
    assert cfg.llm.model_for("validator") == "claude-haiku-4-5-20251001"
    assert resolve_validator_template(spec) == "validator_template"


def test_resolve_strict_swaps_template_only(db_settings: Settings) -> None:
    spec = _registry().resolve("v2_strict_validator")
    cfg = resolve_variant_settings(db_settings, spec)
    assert resolve_validator_template(spec) == "validator_strict"  # ".md" stripped
    assert cfg.llm.provider_for("validator") == "anthropic"
    assert cfg.llm.model_for("validator") == "claude-haiku-4-5-20251001"


def test_resolve_v1_mistral_routes_validator_and_adjuster(db_settings: Settings) -> None:
    spec = _registry().resolve("v1_mistral")
    cfg = resolve_variant_settings(db_settings, spec)
    assert cfg.llm.provider_for("validator") == "mistral"
    assert cfg.llm.provider_for("adjuster") == "mistral"
    assert cfg.llm.model_for("validator") == "mistral-large-2512"
    assert cfg.llm.model_for("adjuster") == "mistral-large-2512"
    # Doc-Parser and Guardrail have no variant slot and stay on the default.
    assert cfg.llm.provider_for("doc_parser") == "anthropic"
    assert cfg.llm.provider_for("guardrail") == "anthropic"
    assert resolve_validator_template(spec) == "validator_template"
    # The shared Settings is untouched (deep copy).
    assert db_settings.llm.provider_for("validator") == "anthropic"


def test_set_provider_rejects_agent_without_variant_slot(db_settings: Settings) -> None:
    llm = db_settings.model_copy(deep=True).llm
    with pytest.raises(ValueError) as exc:
        _set_provider(llm, "guardrail", "mistral")
    assert "validator and adjuster only" in str(exc.value)
    assert "'guardrail'" in str(exc.value)


def test_set_model_rejects_agent_without_variant_slot(db_settings: Settings) -> None:
    llm = db_settings.model_copy(deep=True).llm
    with pytest.raises(ValueError) as exc:
        _set_model(llm, "doc_parser", "some-model")
    assert "validator and adjuster only" in str(exc.value)
    assert "'doc_parser'" in str(exc.value)


# --------------------------------------------------------------------------- #
# Override application
# --------------------------------------------------------------------------- #


def test_build_validator_applies_template_override(
    db_settings: Settings, stub_embedder: Callable[[str], np.ndarray]
) -> None:
    spec = _registry().resolve("v2_strict_validator")
    validator = _build_validator(
        settings=resolve_variant_settings(db_settings, spec),
        user_template_name=resolve_validator_template(spec),
        provider=MockProvider(),
        embedder=stub_embedder,
    )
    assert validator._user_template_name == "validator_strict"


def test_build_validator_applies_model_override_without_mutating_settings(
    db_settings: Settings,
    stub_embedder: Callable[[str], np.ndarray],
    tmp_path: Path,
) -> None:
    # No shipped variant overrides a model since Phase 8.6, so a synthetic registry
    # keeps the model-override path covered. A model with no provider lands in the
    # block of the provider the selector already names (Anthropic by default).
    path = tmp_path / "v.yaml"
    path.write_text(
        _VALID_BODY
        + "  v2_sonnet_validator:\n    description: sonnet\n    validator:\n"
        + "      model: claude-sonnet-4-6\n",
        encoding="utf-8",
    )
    spec = VariantRegistry.load_from_yaml(path).resolve("v2_sonnet_validator")
    original_model = db_settings.llm.model_for("validator")
    validator = _build_validator(
        settings=resolve_variant_settings(db_settings, spec),
        user_template_name=resolve_validator_template(spec),
        provider=MockProvider(),
        embedder=stub_embedder,
    )
    # The override is local to the built agent...
    assert validator._settings.llm.model_for("validator") == "claude-sonnet-4-6"
    assert validator._settings.llm.anthropic.validator_model == "claude-sonnet-4-6"
    # ...and the shared Settings is untouched (deep copy).
    assert db_settings.llm.model_for("validator") == original_model
