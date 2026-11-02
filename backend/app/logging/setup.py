"""
Root logging configuration — the one place `Settings.log_level` is applied.

Why this exists (0.10.0.2): nothing configured Python's root logger. Locally
that was invisible, because the MCP SDK's `basicConfig` happened to install a
console handler at INFO. On Azure the Application Insights distro attaches its
own handler to the root logger first, which makes that later `basicConfig` a
no-op, so the root stayed at WARNING with no console handler and every INFO
line the application writes — the MCP guard's refusal reasons, the tool-call
log lines, the start-up lines — reached neither the container console nor
Application Insights. The guard's diagnostic shipped in 0.10.0.1 and logged
nothing in production for exactly this reason.

Strategy: set the root level from settings, and add one plain console handler
only when no handler already writes to the console, so the local rich handler
is not doubled and the distro's exporter handler is left in place. Idempotent:
a second call changes nothing.
"""

from __future__ import annotations

import logging
import sys
from typing import get_args

from backend.settings import LogLevel

# The console handler this module installs is tagged so a repeat call (tests
# build many apps in one process) recognises it rather than adding another.
_HANDLER_MARKER = "agentic_claims_console_handler"
_CONSOLE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str, logger: logging.Logger | None = None) -> logging.Handler | None:
    """
    Apply `level` to the root logger and ensure the console receives it.

    Returns the handler it installed, or None if a console handler was already
    present. `logger` defaults to the root logger; tests pass a private one so
    the test runner's own capture handlers on the root do not take part.
    Sanitise → validate → abort → execute: the level name is stripped and
    upper-cased, must be one of the settings' allowed values, and only then is
    anything touched.
    """
    name = level.strip().upper()
    allowed = get_args(LogLevel)
    if name not in allowed:
        raise ValueError(f"configure_logging: level must be one of {list(allowed)}; got {level!r}")
    root = logger if logger is not None else logging.getLogger()
    root.setLevel(name)
    if _has_console_handler(root):
        return None
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    return handler


def _has_console_handler(root: logging.Logger) -> bool:
    # A StreamHandler covers the plain case and the test runner's capture; the
    # MCP SDK's RichHandler is not a StreamHandler but does write to the
    # console, so it is recognised by name. The telemetry exporter's handler
    # is neither and must not count — it writes to Application Insights.
    return any(
        isinstance(handler, logging.StreamHandler)
        or type(handler).__name__ == "RichHandler"
        or getattr(handler, _HANDLER_MARKER, False)
        for handler in root.handlers
    )
