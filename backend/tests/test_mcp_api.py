"""
`GET /api/mcp/tools` and `GET /api/mcp/activity`.

The catalogue is read from the server object, so the test asserts the nine
tools, their kinds, the two prompts and the resource, and that `mounted`
follows the token. The feed is tested as the pipeline stream is: a fake bus
whose subscription yields a fixed list and then ends, so the endpoint's
replay-then-live ordering and its de-duplication are observable without an
endless stream.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import TracebackType

import psycopg
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.mcp import get_activity_bus
from backend.app.main import create_app
from backend.app.mcp.models import ToolCallRecord
from backend.app.mcp.tool_log import ToolCallRepository
from backend.app.mcp.tools import TOOL_NAMES
from backend.settings import MCPSettings, Settings


def _record(call_id: int | None, tool: str = "get_run") -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        called_at=datetime.now(UTC),
        tool=tool,
        arguments={},
        target=None,
        caller="shared-token",
        outcome="ok",
        error_class=None,
        latency_ms=3,
    )


class _FakeSubscription:
    def __init__(self, records: list[ToolCallRecord]) -> None:
        self._records = iter(records)

    def __aiter__(self) -> _FakeSubscription:
        return self

    async def __anext__(self) -> ToolCallRecord:
        try:
            return next(self._records)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    def __enter__(self) -> _FakeSubscription:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class _FakeBus:
    def __init__(self, live: list[ToolCallRecord]) -> None:
        self._live = live

    def subscribe(self) -> _FakeSubscription:
        return _FakeSubscription(self._live)


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #


def test_catalogue_lists_the_server_definitions(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/mcp/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mounted"] is False
    assert body["path"] == "/mcp"
    assert [tool["name"] for tool in body["tools"]] == list(TOOL_NAMES)
    kinds = {tool["name"]: tool["kind"] for tool in body["tools"]}
    assert kinds["run_scenario"] == "action"
    assert all(kind == "read" for name, kind in kinds.items() if name != "run_scenario")
    explain = next(tool for tool in body["tools"] if tool["name"] == "explain_decision")
    assert "correlation_id" in explain["parameters"]["properties"]
    assert explain["description"]
    assert [p["name"] for p in body["prompts"]] == ["audit_this_run", "why_settled_or_escalated"]
    assert body["prompts"][0]["arguments"] == [{"name": "correlation_id", "required": True}]
    assert [r["uri"] for r in body["resources"]] == ["policy://excerpt"]
    assert body["resources"][0]["mime_type"] == "text/plain"


def test_catalogue_reports_mounted_when_a_token_is_set(db_settings: Settings) -> None:
    settings = db_settings.model_copy(
        update={"mcp": MCPSettings(shared_token=SecretStr("test-token-not-a-secret"))}
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/mcp/tools").json()
    assert body["mounted"] is True
    # Nothing in the catalogue carries the token.
    assert "test-token-not-a-secret" not in str(body)


# --------------------------------------------------------------------------- #
# Activity feed
# --------------------------------------------------------------------------- #


def _event_ids(text: str) -> list[str]:
    # sse-starlette ends each line with CRLF; `$` under re.M stops before the LF only.
    return re.findall(r"^id: (\d+)\r?$", text, flags=re.M)


def test_activity_replays_then_streams_without_duplicates(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    stored_a = ToolCallRepository.insert(clean_db, _record(None, "list_claims"))
    stored_b = ToolCallRepository.insert(clean_db, _record(None, "get_run"))
    # The live side re-delivers the newest replayed record (the overlap case)
    # and then a genuinely new one.
    live = [stored_b, _record(99, "verify_chain")]
    app = create_app(db_settings)
    app.dependency_overrides[get_activity_bus] = lambda: _FakeBus(live)
    with TestClient(app) as client:
        resp = client.get("/api/mcp/activity")
    assert resp.status_code == 200
    assert _event_ids(resp.text) == [str(stored_a.call_id), str(stored_b.call_id), "99"]
    assert resp.text.count("event: tool_call") == 3
    assert '"tool":"verify_chain"' in resp.text


def test_activity_replay_count_follows_settings(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    for name in ("a", "b", "c"):
        ToolCallRepository.insert(clean_db, _record(None, name))
    settings = db_settings.model_copy(update={"mcp": MCPSettings(activity_replay_count=2)})
    app = create_app(settings)
    app.dependency_overrides[get_activity_bus] = lambda: _FakeBus([])
    with TestClient(app) as client:
        resp = client.get("/api/mcp/activity")
    assert _event_ids(resp.text) == ["2", "3"]


def test_activity_is_empty_but_answers_when_nothing_was_recorded(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    app = create_app(db_settings)
    app.dependency_overrides[get_activity_bus] = lambda: _FakeBus([])
    with TestClient(app) as client:
        resp = client.get("/api/mcp/activity")
    assert resp.status_code == 200
    assert "event: tool_call" not in resp.text
