"""
The `/mcp` route exists only with a token, and only a matching bearer passes.

Each test builds the app with explicit MCP settings and enters the lifespan
(`with TestClient(app)`) so the SDK's session manager is running. The JSON-RPC
`initialize` request is the smallest real message the endpoint accepts.

Mutation proof (recorded in the Phase 10 report, applied / observed / reverted):
replacing the `compare_digest` call in `BearerGuard._authorised` with `True`
fails `test_wrong_token_is_refused` and `test_missing_header_is_refused`;
replacing the mount condition in `mount_mcp` with `True` fails
`test_unset_token_means_no_route`.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.main import create_app
from backend.app.mcp.auth import BearerGuard
from backend.settings import MCPSettings, Settings

_TOKEN = "test-token-not-a-secret"

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
_ACCEPT = {"Accept": "application/json, text/event-stream"}


def _settings(db_settings: Settings, token: str | None) -> Settings:
    mcp = MCPSettings(shared_token=SecretStr(token) if token is not None else None)
    return db_settings.model_copy(update={"mcp": mcp})


def test_missing_header_is_refused(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with TestClient(app) as client:
        resp = client.post("/mcp", json=_INITIALIZE, headers=_ACCEPT)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Bearer realm=")
    assert resp.json() == {"detail": "missing or invalid bearer token"}


def test_wrong_token_is_refused(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", json=_INITIALIZE, headers={**_ACCEPT, "Authorization": "Bearer nope"}
        )
    assert resp.status_code == 401
    # The refusal never echoes what was presented.
    assert "nope" not in resp.text


def test_other_scheme_is_refused(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", json=_INITIALIZE, headers={**_ACCEPT, "Authorization": f"Basic {_TOKEN}"}
        )
    assert resp.status_code == 401


def test_right_token_reaches_the_server(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    assert app.state.mcp_mounted is True
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", json=_INITIALIZE, headers={**_ACCEPT, "Authorization": f"Bearer {_TOKEN}"}
        )
    assert resp.status_code == 200
    assert '"serverInfo"' in resp.text


def test_get_without_token_is_refused(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with TestClient(app) as client:
        assert client.get("/mcp").status_code == 401


def test_unset_token_means_no_route(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, None))
    assert app.state.mcp_mounted is False
    with TestClient(app) as client:
        resp = client.post("/mcp", json=_INITIALIZE, headers=_ACCEPT)
    # FastAPI's ordinary 404 — indistinguishable from any unknown path.
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_blank_token_counts_as_unset(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, "   "))
    assert app.state.mcp_mounted is False


def test_guard_refuses_a_blank_expected_token() -> None:
    async def never(scope: object, receive: object, send: object) -> None:
        raise AssertionError("must not be reached")

    try:
        BearerGuard(never, SecretStr("  "))
    except ValueError as exc:
        assert "must not be blank" in str(exc)
    else:
        raise AssertionError("BearerGuard accepted a blank token")


def test_server_is_built_even_without_a_token(db_settings: Settings) -> None:
    app = create_app(_settings(db_settings, None))
    assert app.state.mcp_server is not None


# --------------------------------------------------------------------------- #
# 0.10.0.1 — every refusal is logged with its reason, never the value
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({}, "header_absent"),
        ({"Authorization": f"Basic {_TOKEN}"}, "scheme_not_bearer"),
        ({"Authorization": "Bearer"}, "scheme_not_bearer"),
        ({"Authorization": "Bearer definitely-not-it"}, "token_mismatch"),
    ],
)
def test_refusal_is_logged_with_its_reason_and_without_the_value(
    db_settings: Settings, caplog: pytest.LogCaptureFixture, headers: dict[str, str], reason: str
) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with (
        caplog.at_level(logging.INFO, logger="backend.app.mcp.auth"),
        TestClient(app) as client,
    ):
        resp = client.post("/mcp", json=_INITIALIZE, headers={**_ACCEPT, **headers})
    assert resp.status_code == 401
    lines = [r.message for r in caplog.records if r.name == "backend.app.mcp.auth"]
    assert lines == [f"mcp auth refused: {reason} (POST /mcp)"]
    assert "definitely-not-it" not in caplog.text and _TOKEN not in caplog.text


def test_success_logs_nothing(db_settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(_settings(db_settings, _TOKEN))
    with (
        caplog.at_level(logging.INFO, logger="backend.app.mcp.auth"),
        TestClient(app) as client,
    ):
        client.post(
            "/mcp", json=_INITIALIZE, headers={**_ACCEPT, "Authorization": f"Bearer {_TOKEN}"}
        )
    assert not [r for r in caplog.records if r.name == "backend.app.mcp.auth"]
