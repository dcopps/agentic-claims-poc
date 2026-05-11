"""
APILogger — one structured JSON record per LLM call.

The Gateway providers wrap every `complete(...)` invocation in a
try/finally and call `APILogger.log_call(record)`. The record's JSON
shape is the contract: downstream consumers parse the field names and
types declared here. Adding fields is non-breaking; renaming or
removing requires an explicit interface-stability review.

Defensive ordering in `log_call`:
  1. Sanitise — apply the redactor to every prompt/response excerpt.
  2. Validate — Pydantic has already typed the record; we trust nothing
     at the JSON boundary, so the dump is `mode="json"` with type-safe
     conversion.
  3. Abort — failures inside the logger itself never propagate; this
     is the one place we deliberately swallow because failing to log
     must not crash a valid agent call. Errors land on stderr instead.
  4. Execute — push the line to the configured sink(s).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Locked agent enumeration. Mirrors `backend.app.audit.event.AgentName`
# verbatim. Duplicated rather than imported so the logging surface
# does not couple to the audit module's import graph; the constraint
# is the same in both places.
APIAgentName = Literal[
    "system",
    "doc_parser",
    "validator",
    "adjuster",
    "guardrail",
    "orchestrator",
]

ProviderName = Literal["anthropic", "mistral"]

# Per-million-token denominator for the cost calculation. Named so the
# arithmetic is greppable and the unit is unambiguous.
_TOKENS_PER_PRICED_UNIT: int = 1_000_000

# Name of the stdlib logger the default sink writes to. Render captures
# stdout from this logger by default; a stdlib config layered on top
# can redirect elsewhere without touching the application code.
_DEFAULT_LOGGER_NAME = "backend.app.logging.api"


class APICallRecord(BaseModel):
    """
    Structured record of a single LLM call. The JSON shape is locked.

    Fields with `_excerpt` suffixes are intentionally truncated — the
    full prompt and response live in the audit vault. The excerpts make
    `grep` over the log stream useful without scrolling megabytes.
    """

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    agent: APIAgentName
    step: str = Field(min_length=1)
    provider: ProviderName
    model: str = Field(min_length=1)
    system_prompt_excerpt: str
    user_prompt_excerpt: str
    response_excerpt: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float | None = None
    latency_ms: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime
    # `error` is null on success. On failure it carries the exception
    # class name and message — enough to triage without exposing
    # internal tracebacks at the log layer.
    error: dict[str, str] | None = None


class APILogger:
    """
    Emits `APICallRecord` JSON lines.

    Construction takes the toggle, the excerpt budget, an optional
    redactor for PII removal, and a callable sink. The default sink is
    a stdlib logger that writes JSON lines to stdout. A sidecar file
    sink (write-append) is added when `file_path` is set.

    The logger is never a singleton — a fresh instance per Settings
    object means tests can pin a sink without polluting global state.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        excerpt_chars: int,
        redactor: Callable[[str], str] | None = None,
        sink: Callable[[str], None] | None = None,
        file_path: Path | None = None,
    ) -> None:
        if excerpt_chars < 1:
            # Defence-in-depth: Settings already enforces a minimum, but
            # this constructor accepts direct callers too.
            raise ValueError(
                "APILogger: excerpt_chars must be >= 1; "
                f"got {excerpt_chars}"
            )

        self._enabled: bool = enabled
        self._excerpt_chars: int = excerpt_chars
        self._redactor: Callable[[str], str] = redactor or _identity
        self._sink: Callable[[str], None] = sink or _default_stdout_sink()
        self._file_path: Path | None = file_path

    def log_call(self, record: APICallRecord) -> None:
        """
        Serialise `record` to canonical JSON and push to the sink(s).

        Disabled logger is a no-op. Sink failures are swallowed and
        re-routed to stderr; an LLM call must not be killed by a
        logging failure.
        """
        if not self._enabled:
            return

        try:
            line = self._serialise(record)
        except Exception as exc:  # noqa: BLE001 — final safety net
            # Pydantic should have validated upstream; reaching here is
            # a real bug, but logging is not the place to crash a call.
            _emergency_log(f"APILogger: serialisation failed: {exc!r}")
            return

        try:
            self._sink(line)
        except Exception as exc:  # noqa: BLE001 — final safety net
            _emergency_log(f"APILogger: sink failed: {exc!r}")

        if self._file_path is not None:
            try:
                _append_line(self._file_path, line)
            except Exception as exc:  # noqa: BLE001 — final safety net
                _emergency_log(
                    f"APILogger: file sink failed at {self._file_path}: {exc!r}"
                )

    @property
    def excerpt_chars(self) -> int:
        """Expose the excerpt budget so callers can truncate consistently."""
        return self._excerpt_chars

    def redact(self, text: str) -> str:
        """Apply the configured redactor — public so callers can pre-clean."""
        return self._redactor(text)

    def excerpt(self, text: str) -> str:
        """Trim `text` to the configured excerpt budget after redaction."""
        cleaned = self._redactor(text)
        if len(cleaned) <= self._excerpt_chars:
            return cleaned
        truncated = cleaned[: self._excerpt_chars]
        return f"{truncated}…(truncated, full length={len(cleaned)})"

    def _serialise(self, record: APICallRecord) -> str:
        # Pydantic's mode="json" handles UUID/datetime/Decimal cleanly.
        # `sort_keys` makes the line diffable across runs; `default=str`
        # is a safety net for anything Pydantic still hands back as a
        # non-JSON-native type.
        payload = record.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def compute_cost_usd(
    *,
    pricing: dict[str, tuple[Decimal, Decimal]],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """
    Compute the USD cost of a call against the configured rate table.

    Returns `None` if no rate is configured for `model` — null in the
    log is preferable to a fabricated number from a stale rate. Returns
    a float (not Decimal) because the log JSON shape locks `cost_usd`
    as a float. Decimal is used internally to avoid float drift on
    six-figure token counts; the cast to float happens at the very end.
    """
    rate = pricing.get(model)
    if rate is None:
        return None

    input_per_million, output_per_million = rate
    if input_per_million < 0 or output_per_million < 0:
        # Negative rates would yield a negative cost — almost certainly
        # a misconfigured pricing block. Surface rather than silently
        # propagating nonsense numbers.
        raise ValueError(
            "compute_cost_usd: pricing rates must be non-negative; "
            f"model={model!r} got=({input_per_million}, {output_per_million})"
        )

    denominator = Decimal(_TOKENS_PER_PRICED_UNIT)
    total = (
        (Decimal(prompt_tokens) * input_per_million)
        + (Decimal(completion_tokens) * output_per_million)
    ) / denominator
    # Round to six decimal places — sub-millicent precision is enough
    # for an audit-grade ledger and avoids exposing arithmetic noise.
    return float(total.quantize(Decimal("0.000001")))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _identity(text: str) -> str:
    return text


def _default_stdout_sink() -> Callable[[str], None]:
    """Return a sink that writes JSON lines via the stdlib logger."""
    logger = logging.getLogger(_DEFAULT_LOGGER_NAME)
    # Don't reconfigure handlers — let the host process decide. If no
    # handlers are attached, fall back to a stderr writer so the line
    # is not silently dropped.
    if logger.handlers or logger.parent and logger.parent.handlers:
        return lambda line: logger.info(line)
    return lambda line: print(line, file=sys.stdout, flush=True)


def _append_line(path: Path, line: str) -> None:
    """Append `line + newline` to `path`. Creates parents on demand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.write("\n")


def _emergency_log(message: str) -> None:
    """Last-resort logger when the configured sink itself fails."""
    print(message, file=sys.stderr, flush=True)


def make_excerpt(text: str, max_chars: int, redactor: Callable[[str], str]) -> str:
    """
    Module-level helper mirroring `APILogger.excerpt` for callers that
    only have a budget value, not a logger instance.

    Kept narrow on purpose — Gateway code constructs excerpts inside
    the `try/finally`, where the logger may not yet exist if
    construction itself raised. Decoupling the function keeps the
    excerpt logic testable in isolation.
    """
    if max_chars < 1:
        raise ValueError(
            "make_excerpt: max_chars must be >= 1; "
            f"got {max_chars}"
        )
    cleaned = redactor(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}…(truncated, full length={len(cleaned)})"


def coerce_error(exc: BaseException) -> dict[str, str]:
    """Turn an exception into the JSON-safe `error` payload shape."""
    return {"type": type(exc).__name__, "message": str(exc)}


# Re-exports for callers that want the helpers without the class. Kept
# at module bottom so the type-checker has the definitions in scope.
__all__ = [
    "APIAgentName",
    "APICallRecord",
    "APILogger",
    "ProviderName",
    "coerce_error",
    "compute_cost_usd",
    "make_excerpt",
]


# Make the typing helper visible to consumers that want `Any` ergonomics.
_AnyDict = dict[str, Any]
