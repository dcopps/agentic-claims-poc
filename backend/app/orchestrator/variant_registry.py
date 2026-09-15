"""
Variant registry — loads and resolves named pipeline variants.

A variant names a set of per-agent overrides applied for one replay run. The
registry loads `variants.yaml` once at startup, validating the schema
declaratively: Literal-typed provider values and `extra="forbid"` reject an
unknown provider or an unknown agent key at load, so a typo in the variants file
fails fast rather than at the first replay.

`resolve(name)` raises `UnknownVariantError` for an unregistered name; the API
layer maps that to 404. The `default` variant must always be present (the
orchestrator's default run resolves it), so its absence is a load-time error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

# Bytes cap — the file is tiny; the bound guards against the path being aimed at
# something large.
_MAX_VARIANTS_BYTES = 64 * 1024

# The variant name that must always be registered.
_DEFAULT_VARIANT = "default"

ProviderName = Literal["anthropic", "mistral"]


class UnknownVariantError(ValueError):
    """Raised when a variant name is not registered. The API maps this to 404."""


class ProviderOverride(BaseModel):
    """Per-agent provider/model override. Either or both of provider / model.

    A `model` without a `provider` replaces the model within whichever provider
    the agent's settings selector already names.
    """

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    provider: ProviderName | None = None


class AgentOverride(ProviderOverride):
    """Validator override: provider / model plus an alternative user template."""

    prompt_template: str | None = None


class VariantSpec(BaseModel):
    """One variant: a description plus optional Validator and Adjuster overrides.

    The Adjuster slot (Phase 8.6) takes a `ProviderOverride`, not an
    `AgentOverride`: the Adjuster has no user-template hook, so a
    `prompt_template` under `adjuster:` must fail at load rather than be silently
    ignored. Doc-Parser and Guardrail slots are intentionally absent — routing
    those agents elsewhere is unverified (adding slots is a future, additive
    change).
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    validator: AgentOverride | None = None
    adjuster: ProviderOverride | None = None


class VariantDocument(BaseModel):
    """The validated shape of `variants.yaml`."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    variants: dict[str, VariantSpec]


class VariantRegistry:
    """Loaded, validated set of named variants."""

    def __init__(self, document: VariantDocument) -> None:
        self._variants = document.variants

    @classmethod
    def load_from_yaml(cls, path: Path) -> VariantRegistry:
        """Load and validate the variants file; fail loudly on any problem."""
        resolved = path.expanduser().resolve()
        raw = _read_variants_text(resolved)
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"VariantRegistry: variants file at {resolved} is not valid YAML; "
                f"error={exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                "VariantRegistry: variants file must parse to a mapping; "
                f"got type={type(parsed).__name__} at {resolved}"
            )
        try:
            document = VariantDocument.model_validate(parsed)
        except PydanticValidationError as exc:
            raise ValueError(
                "VariantRegistry: variants file failed schema validation; "
                f"errors={exc.errors()} path={resolved}"
            ) from exc
        if _DEFAULT_VARIANT not in document.variants:
            raise ValueError(
                "VariantRegistry: variants file must register a "
                f"{_DEFAULT_VARIANT!r} variant; found {sorted(document.variants)}"
            )
        return cls(document)

    def resolve(self, name: str) -> VariantSpec:
        """Return the spec for `name`, or raise `UnknownVariantError`."""
        spec = self._variants.get(name)
        if spec is None:
            raise UnknownVariantError(
                f"VariantRegistry: unknown variant {name!r}; "
                f"registered variants are {sorted(self._variants)}"
            )
        return spec

    def names(self) -> list[str]:
        """All registered variant names, sorted."""
        return sorted(self._variants)


def _read_variants_text(resolved: Path) -> str:
    """Read the variants file with existence / type / size guards."""
    if not resolved.exists():
        raise ValueError(f"VariantRegistry: variants file not found at {resolved}")
    if not resolved.is_file():
        raise ValueError(
            f"VariantRegistry: variants path is not a regular file: {resolved}"
        )
    size = resolved.stat().st_size
    if size > _MAX_VARIANTS_BYTES:
        raise ValueError(
            f"VariantRegistry: variants file too large: {size} bytes at {resolved} "
            f"(cap is {_MAX_VARIANTS_BYTES} bytes)"
        )
    return resolved.read_text(encoding="utf-8")
