"""
End-to-end: the official client over HTTP against a running backend.

Gated on `RUN_MCP_E2E_TESTS=1` with `MCP_E2E_URL` (the backend's `/mcp` URL)
and `MCP_E2E_TOKEN`. Run by hand against a local `uvicorn` with a token before
a deploy, and against each deployed endpoint in the verification pass. The
project carries no pytest-asyncio; each test drives its coroutine with
`asyncio.run`.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import TextResourceContents

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MCP_E2E_TESTS") != "1",
    reason="set RUN_MCP_E2E_TESTS=1, MCP_E2E_URL and MCP_E2E_TOKEN to run",
)

# The SDK's default read timeout is seconds; a scenario run takes about a minute.
_TIMEOUT = httpx2.Timeout(30.0, read=300.0)


def _url() -> str:
    return os.environ["MCP_E2E_URL"]


def _token() -> str:
    return os.environ["MCP_E2E_TOKEN"]


async def _with_client(token: str, scenario: Any) -> Any:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT
    ) as http:
        transport = streamable_http_client(_url(), http_client=http)
        async with Client(transport) as client:
            return await scenario(client)


def test_lists_tools_and_reads_the_policy() -> None:
    async def scenario(client: Client) -> tuple[list[str], str]:
        tools = await client.list_tools()
        excerpt = await client.read_resource("policy://excerpt")
        first = excerpt.contents[0]
        assert isinstance(first, TextResourceContents)
        return [t.name for t in tools.tools], first.text

    names, text = asyncio.run(_with_client(_token(), scenario))
    assert "explain_decision" in names and "run_scenario" in names
    assert "Named Perils" in text


def test_list_claims_and_verify_chain() -> None:
    async def scenario(client: Client) -> tuple[Any, Any]:
        claims = await client.call_tool("list_claims", {})
        assert claims.structured_content is not None
        first = claims.structured_content["claims"][0]
        claim = await client.call_tool("get_claim", {"claim_id": first["claim_id"]})
        assert claim.structured_content is not None
        runs = claim.structured_content["runs"]
        if not runs:
            return claims, None
        chain = await client.call_tool(
            "verify_chain", {"correlation_id": runs[0]["correlation_id"]}
        )
        return claims, chain

    claims, chain = asyncio.run(_with_client(_token(), scenario))
    assert claims.is_error is False
    if chain is not None:
        assert chain.structured_content["scope"] == "whole_ledger"


def test_wrong_token_is_refused() -> None:
    async def scenario(client: Client) -> None:
        await client.list_tools()

    with pytest.raises((MCPError, httpx2.HTTPStatusError, RuntimeError)):
        asyncio.run(_with_client("not-the-token", scenario))
