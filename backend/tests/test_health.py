"""Health endpoint contract test — Phase 0 placeholder satisfies the
'one passing test per stack in CI' definition of done."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok_with_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    # Version comes from importlib.metadata after `uv sync` installs the
    # project. The exact value isn't asserted — only that it's a non-empty
    # string, which catches the "package not installed" regression without
    # coupling the test to the current version literal.
    assert isinstance(body["version"], str)
    assert body["version"] != ""
