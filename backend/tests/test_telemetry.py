"""
Telemetry configurer tests (Phase 9.2).

The property under test is the no-op contract: without a connection string
nothing under `azure.*` or `opentelemetry.*` is imported, which is what
keeps local dev, Render, CI and this suite free of the exporter. The
positive path is exercised against stub modules injected into
`sys.modules`, so no exporter is ever constructed here either. Every guard
clause has a test that asserts the message content.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from pydantic import SecretStr

from backend.app.telemetry import configure_telemetry
from backend.settings import TelemetrySettings

_DISTRO_MODULE = "azure.monitor.opentelemetry"
_PSYCOPG_MODULE = "opentelemetry.instrumentation.psycopg"
_VALID = "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://x.in/"


def _forget_sdk_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop any SDK module another test may have left behind."""
    for name in list(sys.modules):
        if name.startswith(("azure", "opentelemetry")):
            monkeypatch.delitem(sys.modules, name, raising=False)


def _install_stub_sdk(monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, Any]]) -> None:
    """Stand in for the distro and the psycopg instrumentor, recording calls."""
    distro = types.ModuleType(_DISTRO_MODULE)

    def configure_azure_monitor(**kwargs: Any) -> None:
        calls.append(("configure_azure_monitor", kwargs))

    distro.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]

    psycopg_instr = types.ModuleType(_PSYCOPG_MODULE)

    class PsycopgInstrumentor:
        def instrument(self) -> None:
            calls.append(("PsycopgInstrumentor.instrument", None))

    psycopg_instr.PsycopgInstrumentor = PsycopgInstrumentor  # type: ignore[attr-defined]

    # Parent packages must exist for `from a.b.c import x` to resolve via sys.modules.
    for name in ("azure", "azure.monitor", "opentelemetry", "opentelemetry.instrumentation"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, _DISTRO_MODULE, distro)
    monkeypatch.setitem(sys.modules, _PSYCOPG_MODULE, psycopg_instr)


def test_unset_connection_string_is_a_no_op_and_imports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forget_sdk_modules(monkeypatch)

    assert configure_telemetry(TelemetrySettings()) is False

    loaded = [m for m in sys.modules if m.startswith((_DISTRO_MODULE, _PSYCOPG_MODULE))]
    assert loaded == []


def test_whitespace_connection_string_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _forget_sdk_modules(monkeypatch)

    assert configure_telemetry(TelemetrySettings(connection_string=SecretStr("  \n"))) is False
    assert _DISTRO_MODULE not in sys.modules


def test_malformed_connection_string_aborts_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forget_sdk_modules(monkeypatch)
    bogus = "https://kv-example.vault.azure.net/secrets/not-a-connection-string"

    with pytest.raises(ValueError) as excinfo:
        configure_telemetry(TelemetrySettings(connection_string=SecretStr(bogus)))

    message = str(excinfo.value)
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING" in message
    assert "'InstrumentationKey='" in message
    # The operator sees the value they set (truncated), and its length.
    assert bogus[:60] in message
    assert f"({len(bogus)} chars)" in message
    # Validation fails before the SDK is imported.
    assert _DISTRO_MODULE not in sys.modules


def test_valid_connection_string_configures_distro_and_psycopg_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    _install_stub_sdk(monkeypatch, calls)

    result = configure_telemetry(TelemetrySettings(connection_string=SecretStr(f"  {_VALID}  ")))

    assert result is True
    assert calls == [
        # Stripped before it reaches the SDK.
        ("configure_azure_monitor", {"connection_string": _VALID}),
        ("PsycopgInstrumentor.instrument", None),
    ]


def test_create_app_builds_the_class_the_distro_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The FastAPI instrumentor rebinds `fastapi.FastAPI` to a subclass; the app
    must be an instance of whatever that attribute holds when `create_app`
    runs. Regression for Phase 9.2: an import-time `from fastapi import
    FastAPI` kept the original class, so no request reached Application Insights.
    """
    import fastapi

    from backend.app.main import create_app
    from backend.settings import Settings

    class _InstrumentedFastAPI(fastapi.FastAPI):
        pass

    monkeypatch.setattr(fastapi, "FastAPI", _InstrumentedFastAPI)

    app = create_app(Settings())

    assert type(app) is _InstrumentedFastAPI
