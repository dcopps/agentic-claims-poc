"""
MCP support API — the tool catalogue and the live activity feed (Phase 10).

Two read endpoints for the Integrations page, both unauthenticated like the
rest of `/api` and both answering whether or not `/mcp` itself is mounted:

  - `GET /api/mcp/tools` returns the MCP server's own definitions — tools,
    prompts and the resource — generated from the server object on every
    request, so the page cannot drift from what the server offers. `mounted`
    says whether a client can actually connect on this deployment.
  - `GET /api/mcp/activity` streams tool-call records as Server-Sent Events:
    first the last N records from the log (the replay a reconnecting client
    needs), then live records as they are recorded. Each frame's `id` is the
    record's `call_id`, and a record that lands between the replay read and the
    first live frame is sent once, not twice (see the ordering in the source).

Nothing here carries a secret: the records hold ids, a tool name, the caller's
label, an outcome and a latency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.app.mcp import MCP_PATH, ActivityBus, ToolCallRecord, ToolCallRepository
from backend.db.connection import open_connection
from backend.settings import Settings

mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])

# The SSE event name the frontend's feed hook listens for.
ACTIVITY_EVENT = "tool_call"


# --------------------------------------------------------------------------- #
# Catalogue models
# --------------------------------------------------------------------------- #


class ToolView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    title: str | None
    description: str
    kind: Literal["read", "action"]
    parameters: dict[str, Any]


class PromptArgumentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool


class PromptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    title: str | None
    description: str
    arguments: list[PromptArgumentView]


class ResourceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    name: str
    title: str | None
    description: str
    mime_type: str | None


class CatalogueView(BaseModel):
    """What the MCP server offers, and whether it is reachable on this deployment."""

    model_config = ConfigDict(extra="forbid")

    mounted: bool
    path: str
    tools: list[ToolView]
    prompts: list[PromptView]
    resources: list[ResourceView]


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #


def get_mcp_server(request: Request) -> MCPServer:
    server: MCPServer = request.app.state.mcp_server
    return server


def get_mcp_mounted(request: Request) -> bool:
    mounted: bool = request.app.state.mcp_mounted
    return mounted


def get_activity_bus(request: Request) -> ActivityBus:
    bus: ActivityBus = request.app.state.activity_bus
    return bus


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@mcp_router.get("/tools", response_model=CatalogueView)
async def get_catalogue(
    server: MCPServer = Depends(get_mcp_server),
    mounted: bool = Depends(get_mcp_mounted),
) -> CatalogueView:
    """The server's definitions, read from the server object on every request."""
    tools = await server.list_tools()
    prompts = await server.list_prompts()
    resources = await server.list_resources()
    return CatalogueView(
        mounted=mounted,
        path=MCP_PATH,
        tools=[
            ToolView(
                name=tool.name,
                title=tool.title,
                description=tool.description or "",
                # A tool that declares itself read-only is a read; anything
                # else is an action, whatever else its annotations say.
                kind="read" if _read_only(tool.annotations) else "action",
                parameters=dict(tool.input_schema),
            )
            for tool in tools
        ],
        prompts=[
            PromptView(
                name=prompt.name,
                title=prompt.title,
                description=prompt.description or "",
                arguments=[
                    PromptArgumentView(name=arg.name, required=bool(arg.required))
                    for arg in (prompt.arguments or [])
                ],
            )
            for prompt in prompts
        ],
        resources=[
            ResourceView(
                uri=str(resource.uri),
                name=resource.name,
                title=resource.title,
                description=resource.description or "",
                mime_type=resource.mime_type,
            )
            for resource in resources
        ],
    )


@mcp_router.get("/activity")
async def stream_activity(
    settings: Settings = Depends(get_settings),
    bus: ActivityBus = Depends(get_activity_bus),
) -> EventSourceResponse:
    """Replay the last N tool-call records, then stream new ones as they are recorded."""

    async def event_source() -> AsyncIterator[dict[str, str]]:
        # Subscribe before reading the replay so nothing written in between is
        # lost; skip, on the live side, anything the replay already carried.
        with bus.subscribe() as subscription:
            replayed = await run_in_threadpool(
                _recent, settings, settings.mcp.activity_replay_count
            )
            last_replayed = max((r.call_id or 0 for r in replayed), default=0)
            for record in replayed:
                yield _frame(record)
            async for record in subscription:
                if record.call_id is not None and record.call_id <= last_replayed:
                    continue
                yield _frame(record)

    return EventSourceResponse(event_source())


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _read_only(annotations: Any) -> bool:
    return bool(annotations is not None and annotations.read_only_hint)


def _recent(settings: Settings, count: int) -> list[ToolCallRecord]:
    with open_connection(settings) as conn:
        return ToolCallRepository.recent(conn, count)


def _frame(record: ToolCallRecord) -> dict[str, str]:
    return {
        "event": ACTIVITY_EVENT,
        "id": str(record.call_id),
        "data": record.model_dump_json(),
    }
