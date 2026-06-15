#!/usr/bin/env python3
"""
Verify the three scripted demo scenarios against a deployed backend.

Submits each scenario claim, runs the pipeline synchronously, and asserts the
expected outcome. Local-run only (not CI) — it exercises the live LLM agents on
the deployed backend, so it needs the backend's API keys configured there.

    uv run python scripts/verify-demo-scenarios.py --backend https://your-backend.onrender.com

Exits 0 if all three scenarios produce the expected outcome, 1 otherwise. Uses
only the standard library (no new dependency).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

_TIMEOUT_S = 120  # a synchronous run makes several live LLM calls


@dataclass(frozen=True)
class Scenario:
    """One scripted scenario: the claim to submit and what to assert."""

    name: str
    claim: dict[str, object]
    expected_status: str
    expected_rule: str | None  # a fired-rule name that must be present, or None


_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="auto_approve",
        claim={
            "claimant_name": "Harborline Logistics Ltd",
            "policy_number": "CP-2026-9001",
            "loss_date": "2026-04-18",
            "reported_date": "2026-04-19",
            "jurisdiction": "United Kingdom",
            "narrative": "Burst supply line flooded the warehouse; sudden and accidental.",
            "claim_type": "water_damage",
            "reported_amount": "85000.00",
            "scenario_tag": "auto_approve",
        },
        expected_status="settled",
        expected_rule=None,
    ),
    Scenario(
        name="threshold_escalation",
        claim={
            "claimant_name": "Northwood Manufacturing Inc",
            "policy_number": "CP-2026-9002",
            "loss_date": "2026-03-12",
            "reported_date": "2026-03-13",
            "jurisdiction": "United States — New York",
            "narrative": "Overnight electrical fire destroyed the finishing line.",
            "claim_type": "fire",
            "reported_amount": "850000.00",
            "scenario_tag": "threshold_escalation",
        },
        expected_status="awaiting_human",
        expected_rule="settlement_over_ceiling",
    ),
    Scenario(
        name="guardrail_escalation",
        claim={
            "claimant_name": "Coral Bay Holdings",
            "policy_number": "CP-2026-9003",
            "loss_date": "2026-02-28",
            "reported_date": "2026-03-01",
            "jurisdiction": "Bermuda",
            "narrative": "Severe storm; claimant references an unlisted endorsement.",
            "claim_type": "storm_complex",
            "reported_amount": "1400000.00",
            # The tag drives the deterministic demo fixture on the Adjuster.
            "scenario_tag": "guardrail_escalation",
        },
        expected_status="awaiting_human",
        expected_rule="guardrail_failed",
    ),
)


def _post(url: str, body: dict[str, object]) -> dict[str, object]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        result: dict[str, object] = json.loads(resp.read().decode("utf-8"))
    return result


def _run_scenario(backend: str, scenario: Scenario) -> list[str]:
    """Submit + run one scenario; return a list of failure messages (empty == pass)."""
    failures: list[str] = []
    record = _post(f"{backend}/api/claims", scenario.claim)
    claim_id = record["claim_id"]
    correlation_id = str(uuid.uuid4())
    result = _post(
        f"{backend}/api/pipeline/run/{claim_id}?correlation_id={correlation_id}",
        {},
    )

    status = result.get("status")
    if status != scenario.expected_status:
        failures.append(
            f"{scenario.name}: expected status {scenario.expected_status!r}, got {status!r}"
        )

    if scenario.expected_rule is not None:
        decision = result.get("escalation_decision") or {}
        fired = {r["name"] for r in decision.get("fired_rules", [])}  # type: ignore[union-attr]
        if scenario.expected_rule not in fired:
            failures.append(
                f"{scenario.name}: expected rule {scenario.expected_rule!r}; "
                f"fired {sorted(fired)}"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the three demo scenarios live.")
    parser.add_argument(
        "--backend", required=True, help="Backend base URL, e.g. https://app.onrender.com"
    )
    args = parser.parse_args(argv)
    backend = args.backend.rstrip("/")

    all_failures: list[str] = []
    for scenario in _SCENARIOS:
        print(f"→ {scenario.name} …", flush=True)
        try:
            failures = _run_scenario(backend, scenario)
        except urllib.error.URLError as exc:
            failures = [f"{scenario.name}: request failed — {exc}"]
        if failures:
            all_failures.extend(failures)
            for line in failures:
                print(f"  ✗ {line}")
        else:
            print(f"  ✓ {scenario.name} produced the expected outcome")

    if all_failures:
        print(f"\nFAILED: {len(all_failures)} assertion(s) did not hold.")
        return 1
    print("\nOK: all three demo scenarios reproduced the expected outcomes.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
