"""
PromptLoader — the only sanctioned reader of `backend/app/prompts/`.

Strategy: every Markdown file under `system/` or `user/` is a versioned,
externalised prompt. Source code never inlines an f-string for LLM
content — that pattern hides the wording from review and prevents
golden-text tests. `PromptLoader` provides the two reading shapes
agents need:

  - `system(name)` — verbatim read of `system/{name}.md`.
  - `user(name, **kwargs)` — read of `user/{name}.md` followed by
    `.format_map(...)` with a *strict* mapping that raises on any
    placeholder the caller forgot to populate. A typo'd placeholder is
    a hard error, not a silent empty substitution.

Defensive ordering throughout: sanitise → validate → abort → execute.
`name` is rejected if it contains a path separator, `..`, or any
character outside `[A-Za-z0-9_-]` — path traversal guard. Files are
size-capped at `_MAX_PROMPT_BYTES`. The full contents are cached at
class level keyed on `(kind, resolved_path)`; tests clear the cache
via `PromptLoader.clear_cache()` to pick up edits.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Allow alphanumerics, underscore and hyphen. Anything else (slashes,
# dots, spaces) is a path-traversal vector or a non-existent file. The
# regex is anchored so a partial match cannot sneak past.
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Top-level subdirectories the loader recognises. Listed once so the
# error messages and the `_resolve_path` helper share a single source.
_SYSTEM_KIND = "system"
_USER_KIND = "user"
_VALID_KINDS = (_SYSTEM_KIND, _USER_KIND)

# Hard cap on prompt file size. A genuinely larger prompt is a smell —
# split it. The cap also bounds the cost of an accidentally enormous
# file (e.g. someone redirects a model dump into the prompts dir).
_MAX_PROMPT_BYTES = 64 * 1024

# Default base path resolves to the directory of this module — i.e.
# `backend/app/prompts/`. Computed once at import.
_DEFAULT_BASE_PATH = Path(__file__).resolve().parent


class PromptNotFoundError(FileNotFoundError):
    """Raised when the requested prompt file is absent."""


class PromptFormatError(ValueError):
    """Raised when a user-template placeholder is unfilled or unknown."""


class PromptLoader:
    """Loads externalised prompt files. Stateless once constructed."""

    def __init__(self, base_path: Path | None = None) -> None:
        # Resolve once and store — keeps later validation cheap and
        # makes path-traversal checks comparing against an absolute,
        # canonical anchor.
        self._base_path: Path = (base_path or _DEFAULT_BASE_PATH).expanduser().resolve()
        if not self._base_path.is_dir():
            raise ValueError(
                "PromptLoader: base_path must point to an existing directory; "
                f"got {self._base_path}"
            )

    def system(self, name: str) -> str:
        """Return the verbatim contents of `system/{name}.md`."""
        return self._load(_SYSTEM_KIND, name)

    def user(self, name: str, **placeholders: Any) -> str:
        """
        Return `user/{name}.md` formatted with `placeholders`.

        Uses `str.format_map` with a strict mapping that raises
        `PromptFormatError` on any missing placeholder. Unknown
        placeholder keys are silently ignored (they are caller-side
        excess, not a contract break) — only *unfilled* placeholders
        in the template are an error.
        """
        raw = self._load(_USER_KIND, name)
        try:
            return raw.format_map(_StrictMapping(placeholders, prompt_name=name))
        except _MissingPlaceholderError as exc:
            raise PromptFormatError(str(exc)) from exc

    def _load(self, kind: str, name: str) -> str:
        # Sanitise — trim and re-validate so a stray whitespace cannot
        # mask a path-traversal attempt.
        cleaned = name.strip()
        if not cleaned:
            raise PromptFormatError(
                f"PromptLoader: prompt name must be a non-empty string (kind={kind!r})"
            )
        if not _VALID_NAME_RE.fullmatch(cleaned):
            raise PromptFormatError(
                "PromptLoader: prompt name must match "
                f"[A-Za-z0-9_-]+ (kind={kind!r}, got={cleaned!r})"
            )

        # Validate — kind must be one we recognise. Defence-in-depth:
        # the public methods supply the kind, but the private path is
        # not the place for trust.
        if kind not in _VALID_KINDS:
            raise ValueError(
                f"PromptLoader: kind must be one of {_VALID_KINDS}; got {kind!r}"
            )

        resolved = (self._base_path / kind / f"{cleaned}.md").resolve()
        # Path-traversal guard. After resolve(), `resolved` must still
        # live under `_base_path`; symlinks or `..` segments that
        # escaped the regex would surface here.
        if self._base_path not in resolved.parents:
            raise PromptFormatError(
                "PromptLoader: resolved path escapes base directory "
                f"(kind={kind!r}, name={cleaned!r}, resolved={resolved})"
            )

        return _read_prompt_file(resolved)

    @staticmethod
    def clear_cache() -> None:
        """Drop the per-file content cache. Used by tests after edits."""
        _read_prompt_file.cache_clear()


@lru_cache(maxsize=128)
def _read_prompt_file(path: Path) -> str:
    """
    Read `path` and return its contents, with defensive size/emptiness
    guards. Cached so a single test session does not re-read a stable
    prompt file on every call.
    """
    if not path.exists():
        raise PromptNotFoundError(
            f"PromptLoader: prompt file missing at {path}"
        )
    if not path.is_file():
        raise PromptNotFoundError(
            f"PromptLoader: prompt path is not a regular file: {path}"
        )

    size = path.stat().st_size
    if size == 0:
        raise ValueError(
            f"PromptLoader: prompt file is empty at {path} — refusing to load"
        )
    if size > _MAX_PROMPT_BYTES:
        raise ValueError(
            "PromptLoader: prompt file exceeds the size cap; "
            f"path={path} size={size} bytes cap={_MAX_PROMPT_BYTES} bytes"
        )

    # All structural preconditions met — only encoding errors remain.
    return path.read_text(encoding="utf-8")


class _MissingPlaceholderError(KeyError):
    """Internal signal from `_StrictMapping` for missing keys."""


class _StrictMapping(dict[str, Any]):
    """
    A dict that raises `_MissingPlaceholderError` on any missing key.

    Plain `str.format_map(dict)` silently substitutes `''` when the
    underlying dict raises KeyError via __missing__; our subclass
    raises a typed error instead so a typo in the user-template
    placeholder name is a hard error.
    """

    def __init__(self, data: dict[str, Any], *, prompt_name: str) -> None:
        super().__init__(data)
        self._prompt_name = prompt_name

    def __missing__(self, key: str) -> Any:
        raise _MissingPlaceholderError(
            "PromptLoader: missing placeholder "
            f"{key!r} in user template {self._prompt_name!r}; "
            f"supplied keys={sorted(self.keys())}"
        )
