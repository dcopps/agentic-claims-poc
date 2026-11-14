"""
The nine tools through the SDK's in-memory client, against the test database.

`Client(server)` bypasses HTTP and therefore the bearer guard (that is
`test_mcp_auth.py`'s job); what it exercises is the tool logic, the schema
validation the SDK applies to arguments, and the recording of every call.
The orchestrator is the stub the API tests use, injected through
`app.state.orchestrator` — the cache `make_orchestrator_factory` honours.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from mcp import Client
from mcp.types import CallToolResult

from backend.app.escalation.models import EscalationDecision
from backend.app.main import create_app
from backend.app.mcp.tool_log import ToolCallRepository
from backend.app.mcp.tools import TOOL_NAMES
from backend.app.orchestrator.models import EventEmitter, PipelineResult
from backend.settings import Settings
from backend.tests.mcp_fixture import (
    FIXTURE_DISCARDED_QUOTE,
    insert_harborline_claim,
    seed_fixture_run,
    seed_human_decision,
)


@dataclass
class _StubOrchestrator:
    """Records the claim it was asked to run and returns a settled result."""

    ran: list[UUID]

    def run(
        self,
        claim_id: UUID,
        *,
        correlation_id: UUID | None = None,
        emit: EventEmitter | None = None,
        variant: str = "default",
    ) -> PipelineResult:
        self.ran.append(claim_id)
        return PipelineResult(
            status="settled",
            claim_id=claim_id,
            correlation_id=correlation_id or uuid4(),
            escalation_decision=EscalationDecision(
                escalate=False, fired_rules=[], reasoning="stub"
            ),
            doc_parser_output=None,
            validator_output=None,
            adjuster_output=None,
            guardrail_output=None,
            completed_at=datetime.now(UTC),
        )


def _call(
    db_settings: Settings,
    scenario: Callable[[Client], Awaitable[Any]],
    orchestrator: _StubOrchestrator | None = None,
) -> Any:
    """Enter the app lifespan, then drive `scenario` through the in-memory client."""
    app = create_app(db_settings)
    with TestClient(app):
        if orchestrator is not None:
            app.state.orchestrator = orchestrator

        async def run() -> Any:
            async with Client(app.state.mcp_server) as client:
                return await scenario(client)

        return asyncio.run(run())


def _structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False, result.content
    assert result.structured_content is not None
    return dict(result.structured_content)


def _error_text(result: CallToolResult) -> str:
    assert result.is_error is True
    return "".join(getattr(block, "text", "") for block in result.content)


def _last_call(conn: psycopg.Connection) -> tuple[str, str, str | None]:
    row = ToolCallRepository.recent(conn, 1)[0]
    return row.tool, row.outcome, row.error_class


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #


def test_catalogue_lists_exactly_the_nine_tools(db_settings: Settings) -> None:
    async def scenario(client: Client) -> Any:
        return await client.list_tools()

    listing = _call(db_settings, scenario)
    assert [tool.name for tool in listing.tools] == list(TOOL_NAMES)
    read_only = {tool.name: tool.annotations.read_only_hint for tool in listing.tools}
    assert read_only["run_scenario"] is False
    assert all(flag is True for name, flag in read_only.items() if name != "run_scenario")


def test_prompts_and_resource_are_listed(db_settings: Settings) -> None:
    async def scenario(client: Client) -> Any:
        prompts = await client.list_prompts()
        resources = await client.list_resources()
        prompt = await client.get_prompt("audit_this_run", {"correlation_id": "abc-123"})
        excerpt = await client.read_resource("policy://excerpt")
        return prompts, resources, prompt, excerpt

    prompts, resources, prompt, excerpt = _call(db_settings, scenario)
    assert sorted(p.name for p in prompts.prompts) == ["audit_this_run", "why_settled_or_escalated"]
    assert [str(r.uri) for r in resources.resources] == ["policy://excerpt"]
    assert "abc-123" in prompt.messages[0].content.text
    assert "verify_chain" in prompt.messages[0].content.text
    assert "Named Perils" in excerpt.contents[0].text


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #


def test_list_claims_counts_runs(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim = insert_harborline_claim(clean_db)
    seed_fixture_run(clean_db, claim.claim_id)
    seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("list_claims", {})

    data = _structured(_call(db_settings, scenario))
    assert len(data["claims"]) == 1
    assert data["claims"][0]["claim_number"] == claim.claim_number
    assert data["claims"][0]["run_count"] == 2
    assert data["claims"][0]["human_decision"] is None
    assert _last_call(clean_db) == ("list_claims", "ok", None)


def test_list_claims_filters_by_status(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    insert_harborline_claim(clean_db)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("list_claims", {"status": "settled"})

    assert _structured(_call(db_settings, scenario))["claims"] == []


def test_get_claim_and_runs(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("get_claim", {"claim_id": str(claim.claim_id)})

    data = _structured(_call(db_settings, scenario))
    assert data["claim"]["claim_id"] == str(claim.claim_id)
    assert [run["correlation_id"] for run in data["runs"]] == [str(cid)]
    assert data["runs"][0]["status"] == "settled"


def test_get_claim_unknown_is_not_found(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    missing = uuid4()

    async def scenario(client: Client) -> Any:
        return await client.call_tool("get_claim", {"claim_id": str(missing)})

    text = _error_text(_call(db_settings, scenario))
    assert f"not_found: claim {missing}" in text
    assert "Traceback" not in text
    assert _last_call(clean_db) == ("get_claim", "error", "ToolError")


def test_get_run_reports_agents_and_timing(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("get_run", {"correlation_id": str(cid)})

    data = _structured(_call(db_settings, scenario))
    assert data["result"]["status"] == "settled"
    assert data["result"]["adjuster_output"]["recommended_settlement"] == "82500.00"
    assert [row["agent"] for row in data["agents"]] == [
        "doc_parser",
        "validator",
        "adjuster",
        "guardrail",
    ]
    assert data["agents"][1]["model_latency_ms"] == 3144


def test_get_run_unknown_is_not_found(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    missing = uuid4()

    async def scenario(client: Client) -> Any:
        return await client.call_tool("get_run", {"correlation_id": str(missing)})

    assert f"not_found: run {missing}" in _error_text(_call(db_settings, scenario))


def test_explain_decision_worked_example(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("explain_decision", {"correlation_id": str(cid)})

    data = _structured(_call(db_settings, scenario))
    assert data["correlation_id"] == str(cid)
    assert data["claim_number"] == claim.claim_number
    assert data["outcome"]["status"] == "settled"
    discarded = data["guardrail"]["llm_flags_discarded"]
    assert [(d["quote"], d["reason"]) for d in discarded] == [
        (FIXTURE_DISCARDED_QUOTE, "quote_not_a_provision")
    ]
    assert data["chain"] == {
        "scope": "whole_ledger",
        "ok": True,
        "rows_checked": 7,
        "first_break": None,
        "run_rows": 7,
    }
    assert _last_call(clean_db) == ("explain_decision", "ok", None)


def test_explain_decision_unknown_is_not_found(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    missing = uuid4()

    async def scenario(client: Client) -> Any:
        return await client.call_tool("explain_decision", {"correlation_id": str(missing)})

    assert f"not_found: run {missing}" in _error_text(_call(db_settings, scenario))


def test_audit_trail_strips_prompts_by_default(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)
    # The fixture has no prompts (they were stripped at capture); plant one so
    # the default path has something to remove.
    with clean_db.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET payload = jsonb_set(payload, '{llm_call,prompt}', "
            '\'{"system": "S", "user": "U"}\') WHERE correlation_id = %s '
            "AND step = 'coverage_check'",
            (cid,),
        )

    async def scenario(client: Client) -> Any:
        default = await client.call_tool("get_audit_trail", {"correlation_id": str(cid)})
        full = await client.call_tool(
            "get_audit_trail", {"correlation_id": str(cid), "include_prompts": True}
        )
        return default, full

    default, full = _call(db_settings, scenario)
    stripped = _structured(default)
    kept = _structured(full)
    assert stripped["prompts_included"] is False and kept["prompts_included"] is True
    assert len(stripped["entries"]) == 7
    validator_row = next(e for e in stripped["entries"] if e["step"] == "coverage_check")
    assert "prompt" not in validator_row["payload"]["llm_call"]
    validator_full = next(e for e in kept["entries"] if e["step"] == "coverage_check")
    assert validator_full["payload"]["llm_call"]["prompt"] == {"system": "S", "user": "U"}


def test_verify_chain_is_whole_ledger(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim = insert_harborline_claim(clean_db)
    cid_a = seed_fixture_run(clean_db, claim.claim_id)
    seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool("verify_chain", {"correlation_id": str(cid_a)})

    data = _structured(_call(db_settings, scenario))
    assert data["ok"] is True
    assert data["rows_checked"] == 14
    assert data["run_rows"] == 7
    assert data["scope"] == "whole_ledger"


def test_compare_runs_same_claim(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim = insert_harborline_claim(clean_db)
    cid_a = seed_fixture_run(clean_db, claim.claim_id)
    cid_b = seed_fixture_run(clean_db, claim.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "compare_runs", {"correlation_id_a": str(cid_a), "correlation_id_b": str(cid_b)}
        )

    data = _structured(_call(db_settings, scenario))
    assert data["diff"]["settlement_changed"] is False
    assert data["run_a"]["correlation_id"] == str(cid_a)


def test_compare_runs_across_claims_is_refused(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_a = insert_harborline_claim(clean_db)
    claim_b = insert_harborline_claim(clean_db)
    cid_a = seed_fixture_run(clean_db, claim_a.claim_id)
    cid_b = seed_fixture_run(clean_db, claim_b.claim_id)

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "compare_runs", {"correlation_id_a": str(cid_a), "correlation_id_b": str(cid_b)}
        )

    assert "claim_mismatch:" in _error_text(_call(db_settings, scenario))


def test_get_agent_instructions(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    async def scenario(client: Client) -> Any:
        good = await client.call_tool("get_agent_instructions", {"agent": "guardrail"})
        bad = await client.call_tool("get_agent_instructions", {"agent": "orchestrator"})
        return good, bad

    good, bad = _call(db_settings, scenario)
    data = _structured(good)
    assert data["agent"] == "guardrail" and data["variant"] == "default"
    assert "citation" in data["system"].lower()
    assert bad.is_error is True  # refused by the schema: not one of the four


# --------------------------------------------------------------------------- #
# The action tool
# --------------------------------------------------------------------------- #


def test_run_scenario_submits_the_scripted_claim_and_runs_it(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    stub = _StubOrchestrator(ran=[])

    async def scenario(client: Client) -> Any:
        return await client.call_tool("run_scenario", {"name": "harborline"})

    data = _structured(_call(db_settings, scenario, stub))
    assert data["scenario"] == "harborline" and data["status"] == "settled"
    assert [str(c) for c in stub.ran] == [data["claim_id"]]
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT scenario_tag, claimant_name FROM claims WHERE claim_id = %s",
            (data["claim_id"],),
        )
        assert cur.fetchone() == ("auto_approve", "Harborline Logistics Ltd")
    row = ToolCallRepository.recent(clean_db, 1)[0]
    assert row.tool == "run_scenario" and row.target is not None
    assert (row.target.kind, str(row.target.id)) == ("run", data["correlation_id"])


def test_run_scenario_refuses_any_other_name(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    stub = _StubOrchestrator(ran=[])

    async def scenario(client: Client) -> Any:
        return await client.call_tool("run_scenario", {"name": "background_claim_01"})

    result = _call(db_settings, scenario, stub)
    assert result.is_error is True
    assert stub.ran == []
    with clean_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM claims")
        assert cur.fetchone() == (0,)


def test_run_scenario_reruns_an_existing_scripted_claim(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    stub = _StubOrchestrator(ran=[])

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "run_scenario", {"name": "harborline", "claim_id": str(claim.claim_id)}
        )

    data = _structured(_call(db_settings, scenario, stub))
    assert data["claim_id"] == str(claim.claim_id)
    assert stub.ran == [claim.claim_id]
    with clean_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM claims")
        assert cur.fetchone() == (1,)  # no new claim


def test_run_scenario_refuses_a_claim_of_another_scenario(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)  # tagged auto_approve
    stub = _StubOrchestrator(ran=[])

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "run_scenario", {"name": "northwood", "claim_id": str(claim.claim_id)}
        )

    text = _error_text(_call(db_settings, scenario, stub))
    assert "not_a_scripted_claim:" in text and "'auto_approve'" in text
    assert stub.ran == []


def test_run_scenario_refuses_an_unknown_claim_id(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    missing = uuid4()

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "run_scenario", {"name": "harborline", "claim_id": str(missing)}
        )

    assert f"not_found: claim {missing}" in _error_text(
        _call(db_settings, scenario, _StubOrchestrator(ran=[]))
    )


def test_run_scenario_refuses_a_claim_with_a_run_in_flight(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    seed_fixture_run(clean_db, claim.claim_id, steps=("pipeline_started",))

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "run_scenario", {"name": "harborline", "claim_id": str(claim.claim_id)}
        )

    assert "run_in_flight:" in _error_text(_call(db_settings, scenario, _StubOrchestrator(ran=[])))


# Prompt 31: a claim a person has decided is closed, on this route as on the API.
def test_run_scenario_refuses_a_decided_claim(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)
    seed_human_decision(clean_db, claim.claim_id, cid, "approved")
    stub = _StubOrchestrator(ran=[])

    async def scenario(client: Client) -> Any:
        return await client.call_tool(
            "run_scenario", {"name": "harborline", "claim_id": str(claim.claim_id)}
        )

    text = _error_text(_call(db_settings, scenario, stub))
    assert text.endswith(
        f"claim_closed: claim {claim.claim_number} was approved by a person "
        "and is closed to further runs"
    )
    assert stub.ran == []
    assert _last_call(clean_db) == ("run_scenario", "error", "ToolError")


def test_list_claims_says_which_claims_a_person_decided(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)
    seed_human_decision(clean_db, claim.claim_id, cid, "rejected")

    async def scenario(client: Client) -> Any:
        return await client.call_tool("list_claims", {})

    data = _structured(_call(db_settings, scenario))
    assert data["claims"][0]["human_decision"] == "rejected"
