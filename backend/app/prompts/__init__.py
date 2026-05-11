"""
Externalised prompt directory.

Two parallel trees of Markdown files live under here:

  - `system/` — role and format prompts. Loaded verbatim.
  - `user/` — templated user messages. `.format_map(...)` with strict
    placeholder substitution (missing keys raise).

`PromptLoader` is the only sanctioned reader. Source files NEVER carry
inline f-string prompts — that pattern is forbidden by the project's
working protocol so the LLM-facing wording is auditable in one place.
"""

from backend.app.prompts.loader import (
    PromptFormatError,
    PromptLoader,
    PromptNotFoundError,
)

__all__ = ["PromptFormatError", "PromptLoader", "PromptNotFoundError"]
