"""
MCP server over the audit trail (Phase 10).

An MCP client (Claude's connectors, Claude Code, or any other Model Context
Protocol client) can ask the system questions and receive answers taken from
the audit trail — never from re-deciding. The server lives inside the backend,
served at `/mcp` behind a shared bearer token, so it deploys with the backend
to both stacks and shares its settings, logging and process.

Design rules (locked, see the Phase 10 plan):

  1. Answers come from the recorded data; no tool asks a model to judge a claim.
  2. Read-only, with one named exception: `run_scenario`, limited to the three
     scripted scenarios. No human-decision tool, no test bench, no database access.
  3. Every tool call is recorded — tool, arguments, target, caller, latency,
     outcome — in `mcp_tool_calls`, a structured log line and the live feed.
  4. The server is in-process, mounted on the FastAPI app.
  5. Access is explicit: no token, no endpoint.

Public surface:

  - `build_mcp_server` / `mount_mcp` / `MCP_PATH` — construction and mounting.
  - `ActivityBus` / `ToolCallRecorder` — the recording path the feed reads.
  - `ToolCallRecord` and the tool result models — the shapes a client receives.
"""

from backend.app.mcp.activity import ActivityBus
from backend.app.mcp.models import ToolCallRecord
from backend.app.mcp.server import MCP_PATH, build_mcp_server, mount_mcp
from backend.app.mcp.tool_log import ToolCallRecorder, ToolCallRepository

__all__ = [
    "MCP_PATH",
    "ActivityBus",
    "ToolCallRecord",
    "ToolCallRecorder",
    "ToolCallRepository",
    "build_mcp_server",
    "mount_mcp",
]
