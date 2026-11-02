"""
The bearer guard in front of the MCP app.

Why not the SDK's own authentication: it is OAuth-shaped — a token verifier
travels with an issuer URL and a resource-server URL, the server then publishes
protected-resource metadata and answers 401 with a pointer to it, and Claude's
connector flow reads exactly those signals to decide how to sign in. The
prototype has one shared secret and no authorization server, so it checks the
secret itself, in a few lines, before the MCP app sees a byte. Production puts
this behind API Management with Entra sign-in instead.

Behaviour: every HTTP request must carry `Authorization: Bearer <token>`
matching the configured value, compared in constant time. Anything else — no
header, another scheme, a wrong token — gets a 401 with a `WWW-Authenticate`
challenge and a one-line body that never echoes what was sent. Non-HTTP
scopes are refused outright: the endpoint speaks HTTP only.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from pydantic import SecretStr
from starlette.responses import JSONResponse, Response

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_REALM = "agentic-claims-mcp"
_SCHEME = "bearer"


class BearerGuard:
    """ASGI callable: pass the request to `app` only with the right bearer token."""

    def __init__(self, app: ASGIApp, expected: SecretStr) -> None:
        token = expected.get_secret_value().strip()
        # A blank secret would make the comparison trivially satisfiable by a
        # blank header; refuse to be built rather than guard nothing.
        if not token:
            raise ValueError("BearerGuard: the expected token must not be blank")
        self._app = app
        self._expected = token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await Response(status_code=404)(scope, receive, send)
            return
        if not self._authorised(scope):
            await _unauthorised()(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _authorised(self, scope: Scope) -> bool:
        presented = _bearer_token(scope)
        if presented is None:
            return False
        return hmac.compare_digest(presented.encode("utf-8"), self._expected)


def _bearer_token(scope: Scope) -> str | None:
    """The token from `Authorization: Bearer …`, or None if absent or malformed."""
    headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
    for name, value in headers:
        if name.lower() != b"authorization":
            continue
        scheme, _, token = value.decode("latin-1").strip().partition(" ")
        if scheme.lower() != _SCHEME or not token.strip():
            return None
        return token.strip()
    return None


def _unauthorised() -> Response:
    return JSONResponse(
        {"detail": "missing or invalid bearer token"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer realm="{_REALM}"'},
    )
