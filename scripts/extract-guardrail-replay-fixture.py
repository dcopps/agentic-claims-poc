#!/usr/bin/env python3
"""
Extract a recorded Guardrail run from a deployed database into a replay fixture.

Strategy: the audit's `output_check` row holds the literal user prompt the
Guardrail sent (`llm_call.prompt.user`, Phase 8.3). The four template values are
recovered from it by matching the rendered prompt against the template itself,
and the recovery is proven lossless two ways before anything is written: the
template re-rendered from the recovered values must equal the recorded prompt
byte for byte, and the recovered reasoning must equal the full reasoning the
Adjuster's own audit row recorded. Any mismatch aborts with the offset.

Safety: the source is read from REPLAY_SOURCE_DATABASE_URL only — never
DATABASE_URL or TEST_DATABASE_URL — so nothing in Settings, `.env` or the test
guard can be reached by mistake; the connection is read-only; only the hostname
is ever printed; an existing fixture file is never overwritten.

    REPLAY_SOURCE_DATABASE_URL="$(…)" uv run python \\
        scripts/extract-guardrail-replay-fixture.py \\
        --correlation-id <uuid> --label harborline-pass-two-a --expected pass \\
        --source "Azure deployment (Phase 9.2 verification pass two)"

The client-name guard is `backend/tests/test_anonymisation.py`, which scans the
fixture directory in CI. This script runs the Guardrail rule engine's PII
patterns over the fixture text before writing it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit
from uuid import UUID

import psycopg

from backend.app.agents.guardrail_rules import GuardrailRuleEngine
from backend.app.prompts import PromptLoader
from backend.tests.guardrail_replay_fixture import (
    ExpectedVerdict,
    RecordedOutcome,
    ReplayFixture,
    ReplayInputs,
)

_SOURCE_ENV_VAR = "REPLAY_SOURCE_DATABASE_URL"
_DEFAULT_OUT_DIR = Path("backend/tests/fixtures/guardrail_replay")
_EXPECTED_CHOICES: tuple[ExpectedVerdict, ...] = ("pass", "flag_hallucinated_citation")
_LABEL_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Placeholder syntax of the user templates (`{name}`); the recovery regex is
# derived from the template so it can never drift from what the agent renders.
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class ExtractionRequest:
    """Validated command-line input."""

    correlation_id: UUID
    label: str
    expected: ExpectedVerdict
    source: str
    out_path: Path


@dataclass(frozen=True)
class RecordedRun:
    """The two audit rows a fixture is built from."""

    output_check: dict[str, Any]
    recorded_at: datetime
    settlement_estimate: dict[str, Any]


def main(argv: list[str] | None = None) -> int:
    request = _validate(_parse_args(argv))
    if request.out_path.exists():
        _fail(f"refusing to overwrite existing fixture {request.out_path}")
    url = _source_url()
    loader = PromptLoader()
    run = _read_run(url, request.correlation_id)
    inputs = _recover_inputs(_recorded_user_prompt(run), loader)
    _assert_round_trip(loader, inputs, _recorded_user_prompt(run))
    _assert_matches_adjuster_row(inputs, run.settlement_estimate)
    fixture = _build_fixture(request, run, inputs)
    text = json.dumps(fixture.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    _assert_no_pii(text)
    request.out_path.write_text(text, encoding="utf-8")
    print(f"→ wrote {request.out_path} ({len(text)} bytes, expected={request.expected})")
    return 0


# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a recorded Guardrail run into a replay fixture (read-only)."
    )
    parser.add_argument("--correlation-id", required=True, help="Pipeline run correlation id.")
    parser.add_argument("--label", required=True, help="Kebab-case fixture label.")
    parser.add_argument("--expected", required=True, choices=_EXPECTED_CHOICES)
    parser.add_argument("--source", required=True, help="Where the run was recorded.")
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR), help="Fixture directory.")
    return parser.parse_args(argv)


def _validate(args: argparse.Namespace) -> ExtractionRequest:
    """Sanitise and validate every argument before touching the network."""
    try:
        correlation_id = UUID(args.correlation_id.strip())
    except ValueError:
        _fail(f"--correlation-id must be a UUID; got {args.correlation_id!r}")
    label = args.label.strip()
    if not _LABEL_RE.fullmatch(label):
        _fail(f"--label must be kebab-case [a-z0-9-]; got {args.label!r}")
    source = args.source.strip()
    if not source:
        _fail("--source must be a non-empty description of where the run was recorded")
    out_dir = Path(args.out_dir)
    if not out_dir.is_dir():
        _fail(f"--out-dir must be an existing directory; got {out_dir}")
    out_path = out_dir / f"{str(correlation_id)[:8]}-{label}.json"
    return ExtractionRequest(correlation_id, label, args.expected, source, out_path)


def _source_url() -> str:
    """Read the source database URL from its dedicated variable; echo the host only."""
    url = os.environ.get(_SOURCE_ENV_VAR, "").strip()
    if not url:
        _fail(
            f"{_SOURCE_ENV_VAR} is not set. This script never reads DATABASE_URL or "
            "TEST_DATABASE_URL; export the source explicitly."
        )
    host = urlsplit(url).hostname
    if not host:
        _fail(f"{_SOURCE_ENV_VAR} does not parse as a database URL with a hostname")
    print(f"→ source host: {host}")
    return url


# --------------------------------------------------------------------------- #
# Reading the audit rows (read-only)
# --------------------------------------------------------------------------- #


def _read_run(url: str, correlation_id: UUID) -> RecordedRun:
    """Open a read-only connection and fetch the two rows the fixture needs."""
    try:
        with psycopg.connect(url) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                output_check, recorded_at = _fetch_step(cur, correlation_id, "output_check")
                settlement, _ = _fetch_step(cur, correlation_id, "settlement_estimate")
    except psycopg.OperationalError as exc:
        _fail(f"cannot connect to the source database: {type(exc).__name__}")
    return RecordedRun(output_check, recorded_at, settlement)


def _fetch_step(
    cur: psycopg.Cursor[Any], correlation_id: UUID, step: str
) -> tuple[dict[str, Any], datetime]:
    """Return exactly one audit payload for the step, or abort with the count found."""
    cur.execute(
        "SELECT payload, created_at FROM audit_log WHERE correlation_id = %s AND step = %s",
        (correlation_id, step),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        _fail(f"expected exactly one '{step}' audit row for {correlation_id}; found {len(rows)}")
    payload, created_at = rows[0]
    if not isinstance(payload, dict):
        _fail(f"'{step}' payload for {correlation_id} is {type(payload).__name__}, not an object")
    return payload, created_at


def _recorded_user_prompt(run: RecordedRun) -> str:
    """The literal user prompt the Guardrail sent (Phase 8.3 `llm_call.prompt.user`)."""
    prompt = run.output_check.get("llm_call", {}).get("prompt")
    if not isinstance(prompt, dict) or not isinstance(prompt.get("user"), str):
        _fail("output_check row has no llm_call.prompt.user — recorded before Phase 8.3?")
    user: str = prompt["user"]
    return user


# --------------------------------------------------------------------------- #
# Recovering the template values and proving the recovery lossless
# --------------------------------------------------------------------------- #


def _recover_inputs(user_prompt: str, loader: PromptLoader) -> ReplayInputs:
    """
    Match the rendered prompt against the template, turning each `{name}` into a
    capture group. The literal text between placeholders is escaped verbatim, so
    the only way the match succeeds is for the prompt to be an instance of the
    template; the round-trip check afterwards proves the capture was exact.
    """
    template = loader.raw("user", "guardrail_template")
    parts = _PLACEHOLDER_RE.split(template)
    pattern = "".join(
        re.escape(part) if index % 2 == 0 else f"(?P<{part}>.*?)"
        for index, part in enumerate(parts)
    )
    match = re.compile(pattern, re.DOTALL).fullmatch(user_prompt)
    if match is None:
        _fail("recorded user prompt does not match the current guardrail_template")
    return ReplayInputs(**match.groupdict())


def _assert_round_trip(loader: PromptLoader, inputs: ReplayInputs, recorded: str) -> None:
    rendered = loader.user("guardrail_template", **inputs.model_dump())
    if rendered != recorded:
        _fail(
            "re-rendering the template from the recovered values does not reproduce the "
            f"recorded prompt (rendered {len(rendered)} chars, recorded {len(recorded)}, "
            f"first difference at offset {_first_difference(rendered, recorded)})"
        )


def _assert_matches_adjuster_row(inputs: ReplayInputs, settlement_payload: dict[str, Any]) -> None:
    """The Adjuster's own audit row (Phase 5 full `reasoning`) must agree with the recovery."""
    output = settlement_payload.get("output") or {}
    reasoning = output.get("reasoning")
    settlement = output.get("recommended_settlement")
    if reasoning != inputs.adjuster_reasoning:
        offset = _first_difference(str(reasoning), inputs.adjuster_reasoning)
        _fail(
            "recovered reasoning differs from the settlement_estimate row's reasoning "
            f"(first difference at offset {offset})"
        )
    if str(settlement) != inputs.adjuster_settlement:
        _fail(
            f"recovered settlement {inputs.adjuster_settlement!r} differs from the "
            f"settlement_estimate row's {settlement!r}"
        )


def _first_difference(left: str, right: str) -> int:
    for offset, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return offset
    return min(len(left), len(right))


# --------------------------------------------------------------------------- #
# Building and checking the fixture
# --------------------------------------------------------------------------- #


def _build_fixture(
    request: ExtractionRequest, run: RecordedRun, inputs: ReplayInputs
) -> ReplayFixture:
    output = run.output_check.get("output") or {}
    flags = output.get("flags") or []
    system_prompt = run.output_check["llm_call"]["prompt"].get("system", "")
    return ReplayFixture(
        correlation_id=request.correlation_id,
        label=request.label,
        recorded_at=run.recorded_at,
        source=request.source,
        expected=request.expected,
        recorded_outcome=RecordedOutcome(
            passed=bool(output.get("passed")),
            rule_flags=[flag for flag in flags if flag.get("source") == "rule"],
            llm_flags=[flag for flag in flags if flag.get("source") == "llm"],
        ),
        recorded_system_prompt_sha256=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        inputs=inputs,
    )


def _assert_no_pii(text: str) -> None:
    """Run the Guardrail's own PII patterns over the file text; a hit aborts the write."""
    for name, pattern in GuardrailRuleEngine.with_defaults().pii_patterns:
        if pattern.search(text):
            _fail(f"fixture text matches the Guardrail PII pattern {name!r}; not written")


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
