"""
LLM Gateway — the only sanctioned path to a Claude or Mistral call.

`LLMProvider` is the abstract interface every agent's outgoing LLM
call passes through. `AnthropicProvider` and `MistralProvider` are the
two concrete implementations. `LLMProviderError` is the single error
type the wrappers raise — call sites catch one type at the API
boundary regardless of which vendor failed.

`get_provider(settings, vendor)` is the construction factory. It
validates the API key is present, instantiates the underlying SDK
client once, and caches the resulting provider per `(settings, vendor)`
so callers do not pay for repeated construction.

The interface enforces system / user message separation by accepting
them as separate keyword-only arguments. Providers translate to
vendor-specific SDK shapes (Anthropic's top-level `system` parameter,
Mistral's first-message-with-role-system convention) inside the
wrapper, never at the call site.
"""

from backend.app.llm.anthropic_provider import AnthropicProvider
from backend.app.llm.factory import get_provider
from backend.app.llm.mistral_provider import MistralProvider
from backend.app.llm.provider import (
    LLMProvider,
    LLMProviderError,
    ProviderResponse,
    ResponseFormat,
)

__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LLMProviderError",
    "MistralProvider",
    "ProviderResponse",
    "ResponseFormat",
    "get_provider",
]
