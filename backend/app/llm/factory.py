"""
Provider factory — the only sanctioned way to construct a provider.

`get_provider(settings, vendor)` returns a cached `LLMProvider` keyed on
`(id(settings), vendor)`. A single `Settings` object yields one
provider per vendor; tests with stub Settings get their own instances
without polluting the production cache.

Constructing through the factory ensures:

  - The API key is checked at construction time (no opaque 401 later).
  - The APILogger is built from the same Settings the provider uses.
  - Pricing rates from `Settings.llm.pricing` propagate to the provider
    so the APILogger can populate `cost_usd`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr

from backend.app.llm.anthropic_provider import AnthropicProvider
from backend.app.llm.mistral_provider import MistralProvider
from backend.app.llm.provider import LLMProvider
from backend.app.logging.api_logger import APILogger
from backend.settings import Settings

ProviderVendor = Literal["anthropic", "mistral"]

# Module-level cache. `Settings` is a Pydantic model (mutable, unhashable)
# so `lru_cache` cannot key on it directly; we key on the identity of
# the instance plus the vendor name. Bounded by the number of distinct
# Settings instances the application constructs — production has one,
# tests have a handful, so the dict never grows large.
_PROVIDER_CACHE: dict[tuple[int, ProviderVendor], LLMProvider] = {}


def get_provider(settings: Settings, vendor: ProviderVendor) -> LLMProvider:
    """Return a memoised `LLMProvider` for `vendor` built from `settings`."""
    if vendor not in ("anthropic", "mistral"):
        # Defensive — `Literal` should have caught this at the type
        # level, but we own the boundary so we re-assert.
        raise ValueError(
            f"get_provider: vendor must be 'anthropic' or 'mistral'; got {vendor!r}"
        )

    cache_key = (id(settings), vendor)
    cached = _PROVIDER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    provider = _build(settings, vendor)
    _PROVIDER_CACHE[cache_key] = provider
    return provider


def _build(settings: Settings, vendor: ProviderVendor) -> LLMProvider:
    """Construct a fresh provider plus its APILogger from `settings`."""
    api_logger = APILogger(
        enabled=settings.logging.api_log_enabled,
        excerpt_chars=settings.logging.api_log_excerpt_chars,
        file_path=settings.logging.api_log_path,
    )
    if vendor == "anthropic":
        return AnthropicProvider(
            api_key=_require_key(settings.llm.anthropic.api_key, "ANTHROPIC_API_KEY"),
            api_logger=api_logger,
            pricing=settings.llm.pricing,
        )
    return MistralProvider(
        api_key=_require_key(settings.llm.mistral.api_key, "MISTRAL_API_KEY"),
        api_logger=api_logger,
        pricing=settings.llm.pricing,
    )


def _require_key(key: SecretStr | None, env_name: str) -> SecretStr:
    """Refuse a missing API key with a clear, env-aware error message."""
    if key is None or not key.get_secret_value().strip():
        raise ValueError(
            f"get_provider: {env_name} is not set — "
            "populate the environment variable or settings.yaml before constructing a provider"
        )
    return key


def clear_provider_cache() -> None:
    """Drop the memoised providers. Used by tests after stubbing."""
    _PROVIDER_CACHE.clear()
