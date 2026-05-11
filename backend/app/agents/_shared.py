"""
Shared helpers used by every agent in `backend.app.agents`.

This is a *helper module*, not a base class. Phase 3's plan rejected
introducing a `BaseAgent` inheritance layer — the contents of each
agent's pipeline differ enough that a template-method skeleton would
read worse than independent files. What does duplicate, on the other
hand, is mechanical: extracting a JSON object from a possibly
prose-wrapped response, truncating long strings for audit excerpts,
clamping floats to the unit interval, minting a per-call correlation
id for the API logger.

Those helpers live here so every agent can import them by name and so
the test surface for the helpers themselves is one file (`_shared.py`)
rather than four near-identical copies.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

# Regex that finds the outermost `{...}` block in a string. Used to
# rescue a JSON payload from a model that wrapped its output in prose
# or Markdown fences. The flag `re.DOTALL` lets `.` cross newlines so
# multi-line JSON stays in one match.
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_block(text: str, *, agent_name: str) -> str:
    """
    Return the outermost JSON object embedded in `text`.

    A well-behaved model returns a bare JSON object; a misbehaving one
    wraps it in prose or Markdown fences. Both shapes are accepted by
    this helper. A response with no `{...}` at all is a hard error —
    no amount of cleanup recovers JSON from text that does not contain
    any.

    `agent_name` is woven into the error message so the audit-log
    `error.message` field identifies which agent's parser raised
    without the caller having to wrap.
    """
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        raise ValueError(
            f"{agent_name}: model response contains no `{{...}}` block; "
            f"excerpt={text[:500]!r}"
        )
    return match.group(0)


def excerpt(text: str, max_chars: int) -> str:
    """
    Truncate `text` to `max_chars` with a length-suffix marker.

    Used to size prompt narratives, retrieved chunks, and reasoning
    fields down to a human-reviewable excerpt for the audit-log
    payload. Full content remains in the upstream artefacts (claim
    row, retrieved chunks, model raw response) — the excerpt is for
    triage, not forensic reconstruction.
    """
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}…(truncated, full length={len(text)})"


def clamp_unit(value: float) -> float:
    """Clamp `value` to `[0, 1]` — defensive against arithmetic edge cases."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def new_correlation_id() -> UUID:
    """
    Generate a fresh UUID for the APILogger record.

    Agents thread the caller's correlation id through to the audit
    log (which is what links a pipeline run together); the LLM-call
    record carries its own UUID so future retry support can
    distinguish multiple attempts within one agent run.
    """
    return uuid4()
