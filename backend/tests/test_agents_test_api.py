"""
Tests for the agent test bench API.

The guard tests (malformed body → 422, unknown variant → 404) and the prompt-source
endpoint run in CI — they fail before any provider call. The happy-path probe
endpoints make real LLM calls and are gated (`RUN_LLM_E2E_TESTS=1`).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.settings import Settings

_GATED = pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with ANTHROPIC_API_KEY for live agent-test calls.",
)


# --------------------------------------------------------------------------- #
# Prompt-source endpoint (CI — no keys)
# --------------------------------------------------------------------------- #


def test_prompt_endpoint_default(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/agents/validator/prompt")
    assert resp.status_code == 200
    body = resp.json()
    assert "coverage validator" in body["system"]
    assert "{claim_narrative}" in body["user"]  # unformatted template
    assert body["variant"] == "default"


def test_prompt_endpoint_strict_variant_swaps_user_template(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/agents/validator/prompt?variant=v2_strict_validator")
    assert resp.status_code == 200
    assert "strict review" in resp.json()["user"].lower()


def test_prompt_endpoint_unknown_agent_404(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/agents/wizard/prompt")
    assert resp.status_code == 404


def test_prompt_endpoint_unknown_variant_404(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/agents/validator/prompt?variant=v9_unreal")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Test-endpoint guards (CI — no keys; fail before any provider call)
# --------------------------------------------------------------------------- #


def test_doc_parser_blank_narrative_422(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post("/api/agents/test/doc-parser", json={"narrative": ""})
    assert resp.status_code == 422


def test_doc_parser_unknown_variant_404(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(
            "/api/agents/test/doc-parser?variant=v9_unreal",
            json={"narrative": "Burst pipe."},
        )
    assert resp.status_code == 404


def test_validator_missing_claim_type_422(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post("/api/agents/test/validator", json={"narrative": "Burst pipe."})
    assert resp.status_code == 422


def test_adjuster_malformed_body_422(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post("/api/agents/test/adjuster", json={"doc_parser_output": {}})
    assert resp.status_code == 422


def test_guardrail_malformed_body_422(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post("/api/agents/test/guardrail", json={"retrieved_chunks": []})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Gated real-call happy paths
# --------------------------------------------------------------------------- #


@_GATED
def test_doc_parser_probe_live(db_settings: Settings) -> None:
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(
            "/api/agents/test/doc-parser",
            json={
                "narrative": (
                    "Burst supply line flooded the warehouse on 18 April 2026 at "
                    "Acme Ltd in the United Kingdom; loss about USD 85,000."
                )
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["output"]["claim_type"]
    assert body["meta"]["model"]
