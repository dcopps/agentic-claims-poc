"""
Build the MCP server and, when a token is configured, mount it at `/mcp`.

Two facts shape this module:

  - **The server object always exists.** `GET /api/mcp/tools` lists the
    server's own definitions whether or not the endpoint is reachable, so the
    Integrations page can explain what the server would offer on a deployment
    that has not configured a token.
  - **The endpoint exists only with a token.** `mount_mcp` registers the route
    when `mcp.shared_token` is set and does nothing otherwise — a request to
    `/mcp` then gets the app's ordinary 404. There is no anonymous mode.

Mounting is an exact-path route, not a `Mount`: a sub-application mounted at
`/mcp` answers `GET /mcp` with a redirect to `/mcp/`, and behind the Render and
Azure TLS terminators that redirect is emitted as `http://`, which the MCP
client refuses by design. An exact route hands `/mcp` to the SDK's app
unchanged, with no redirect and no dependency on forwarded headers.

The SDK's DNS-rebinding protection is switched off for this route: by default
it rejects every `Host` but localhost, both deployments sit behind an ingress
that owns the `Host` header, and the bearer token is the access control.
"""

from __future__ import annotations

import logging

import fastapi
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from backend.app.api.health import resolve_version
from backend.app.mcp.auth import BearerGuard
from backend.app.mcp.templates import register_templates
from backend.app.mcp.tools import register_tools
from backend.settings import Settings

_logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"

# Streamable HTTP is POST for messages, GET for the server-initiated stream and
# DELETE to end a session; nothing else is part of the transport.
_MCP_METHODS = ["GET", "POST", "DELETE"]

_INSTRUCTIONS = (
    "This server answers questions about insurance claims from the system's audit trail. "
    "Every answer is taken from recorded data; no tool re-decides a claim. The tools are "
    "read-only except run_scenario, which runs one of three scripted demonstration claims. "
    "Cite the audit row ids the tools return."
)


def build_mcp_server(app: fastapi.FastAPI) -> MCPServer:
    """The server with its nine tools, two prompts and one resource, bound to `app`."""
    settings: Settings = app.state.settings
    server = MCPServer(
        name=settings.app_name, version=resolve_version(), instructions=_INSTRUCTIONS
    )
    register_tools(server, app)
    register_templates(server, settings)
    return server


def mount_mcp(app: fastapi.FastAPI, server: MCPServer, settings: Settings) -> bool:
    """
    Register `/mcp` behind the bearer guard if a token is configured.

    Returns whether the route was registered, so the lifespan knows whether
    to run the session manager and the catalogue endpoint can say so.
    """
    token = settings.mcp.shared_token
    if token is None:
        _logger.info("mcp endpoint not mounted: MCP__SHARED_TOKEN unset")
        return False
    asgi = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        # No tool uses the server-to-client back-channel (no elicitation,
        # sampling or progress), and a stateless server survives a scale-to-
        # zero restart or a second replica without sticky sessions.
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    # `Route` with an ASGI callable as its endpoint (Starlette treats any
    # non-function endpoint as an ASGI app) — the exact-path form described above.
    guarded = BearerGuard(asgi, token)
    app.router.routes.append(Route(MCP_PATH, endpoint=guarded, methods=_MCP_METHODS))
    _logger.info("mcp endpoint mounted at %s", MCP_PATH)
    return True
