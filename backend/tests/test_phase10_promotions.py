"""
The four functions Phase 10 promoted out of the routers so the MCP tools and
the API share them: `AuditRepository.list_entries` / `has_entries`,
`RunsRepository.count_runs_by_claim`, `make_orchestrator_factory` and
`load_agent_prompts`. The routers' own tests still pass unchanged, which is
the proof that no HTTP shape moved; these cover the functions directly.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.api.agents_test import UnknownAgentError, load_agent_prompts
from backend.app.api.pipeline import make_orchestrator_factory
from backend.app.audit import AuditRepository
from backend.app.main import create_app
from backend.app.orchestrator.variant_registry import UnknownVariantError
from backend.app.runs import RunsRepository
from backend.settings import Settings
from backend.tests.mcp_fixture import insert_harborline_claim, seed_fixture_run


def test_list_entries_in_chain_order_and_has_entries(clean_db: psycopg.Connection) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)
    entries = AuditRepository.list_entries(clean_db, cid)
    assert [e.step for e in entries] == [
        "pipeline_started",
        "doc_extract",
        "coverage_check",
        "settlement_estimate",
        "output_check",
        "escalation_decision",
        "pipeline_settled",
    ]
    assert [e.audit_id for e in entries] == sorted(e.audit_id for e in entries)
    assert all(len(e.chain_hash) == 64 for e in entries)
    assert AuditRepository.has_entries(clean_db, cid) is True
    assert AuditRepository.has_entries(clean_db, uuid4()) is False
    assert AuditRepository.list_entries(clean_db, uuid4()) == []


def test_count_runs_by_claim(clean_db: psycopg.Connection) -> None:
    with_runs = insert_harborline_claim(clean_db)
    without = insert_harborline_claim(clean_db)
    seed_fixture_run(clean_db, with_runs.claim_id)
    seed_fixture_run(clean_db, with_runs.claim_id, steps=("pipeline_started",))  # in flight
    counts = RunsRepository.count_runs_by_claim(
        clean_db, [with_runs.claim_id, without.claim_id, uuid4()]
    )
    assert counts == {with_runs.claim_id: 2}
    assert RunsRepository.count_runs_by_claim(clean_db, []) == {}


def test_factory_returns_the_cached_default_orchestrator(db_settings: Settings) -> None:
    app = create_app(db_settings)
    sentinel = object()
    with TestClient(app):
        app.state.orchestrator = sentinel
        factory = make_orchestrator_factory(app)
        assert factory("default") is sentinel
        with pytest.raises(UnknownVariantError):
            factory("no_such_variant")


def test_load_agent_prompts(db_settings: Settings) -> None:
    app = create_app(db_settings)
    with TestClient(app):
        registry = app.state.variant_registry
        view = load_agent_prompts("doc-parser", "default", registry)
        assert view.agent == "doc_parser"
        assert view.system and view.user
        with pytest.raises(
            UnknownAgentError, match="unknown agent: 'orchestrator'; expected one of"
        ):
            load_agent_prompts("orchestrator", "default", registry)
        with pytest.raises(UnknownVariantError):
            load_agent_prompts("validator", "no_such_variant", registry)
