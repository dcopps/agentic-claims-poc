"""
Application Insights export via the Azure Monitor OpenTelemetry distro (Phase 9.2).

Strategy: the connection string is the only switch, and the SDK is a
*lazy* import. `configure_telemetry` returns before touching anything under
`azure.*` or `opentelemetry.*` when the string is absent, so local
development, Render, CI and the test suite never load the exporter, never
open a network path to an ingestion endpoint and pay nothing at start-up.
When the string is present it is validated for shape first — a value that
cannot be a connection string is a deployment error to surface, not
something to hand to the SDK and discover in the portal.

What the distro captures once configured: every FastAPI request (the
distro rebinds the module attribute `fastapi.FastAPI` to an instrumented
subclass, so the app must be constructed *after* this call and through
`fastapi.FastAPI` looked up at that moment — a `from fastapi import FastAPI`
taken at import keeps the original class), unhandled exceptions, outbound
`httpx` calls (the Anthropic and Mistral SDKs) as dependencies, and Python
logging. Postgres is reached through psycopg 3, which the distro does not
bundle, so its instrumentor is enabled here explicitly.

Probe traffic on `/health` is excluded from request telemetry by the
`OTEL_PYTHON_EXCLUDED_URLS` environment variable the Container App sets —
OpenTelemetry's own configuration surface, read by the instrumentor at
configure time, not a setting this module interprets.
"""

from __future__ import annotations

from backend.settings import TelemetrySettings

# The distro accepts several key=value pairs; this one is the component's
# identity and the only pair every valid string carries. Checking for it
# catches the realistic mistakes (a stray resource id, a vault URI, "true").
_REQUIRED_KEY = "InstrumentationKey="

# Long enough to recognise the value in a message, short enough that a
# mis-set secret is not echoed in full to logs.
_MESSAGE_EXCERPT_CHARS = 60


def configure_telemetry(settings: TelemetrySettings) -> bool:
    """
    Start Application Insights export if, and only if, a connection string is set.

    Sanitise → validate → abort → execute: strip the value; an empty result is
    the documented "telemetry off" state and returns False without importing
    the SDK; a non-empty value without the instrumentation-key pair raises
    ValueError naming what was expected and what was found; otherwise the
    distro and the psycopg instrumentor are configured and True is returned.
    """
    connection_string = _resolve_connection_string(settings)
    if not connection_string:
        return False

    _require_connection_string_shape(connection_string)

    # All preconditions met — only now does the SDK enter the process.
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    configure_azure_monitor(connection_string=connection_string)
    PsycopgInstrumentor().instrument()
    return True


def _resolve_connection_string(settings: TelemetrySettings) -> str:
    """Unwrap the secret and strip it; None and whitespace both mean unset."""
    if settings.connection_string is None:
        return ""
    return settings.connection_string.get_secret_value().strip()


def _require_connection_string_shape(connection_string: str) -> None:
    # A value without the key pair cannot reach any component: fail here with
    # the operator's own value in view rather than let the exporter retry
    # silently against nothing.
    if _REQUIRED_KEY not in connection_string:
        excerpt = connection_string[:_MESSAGE_EXCERPT_CHARS]
        raise ValueError(
            "APPLICATIONINSIGHTS_CONNECTION_STRING is set but is not an Application "
            f"Insights connection string: expected a value containing {_REQUIRED_KEY!r}, "
            f"got {excerpt!r} ({len(connection_string)} chars). Unset it to run without "
            "telemetry."
        )
