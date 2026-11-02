"""
`configure_logging`: the root level follows settings, and INFO reaches the
console even when only the telemetry exporter's handler is on the root logger
— the Azure situation that silenced the guard's diagnostic in 0.10.0.1.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from backend.app.logging.setup import configure_logging


class _ExporterHandler(logging.Handler):
    """Stands in for the Azure Monitor distro's handler: not a StreamHandler."""

    def emit(self, record: logging.LogRecord) -> None:
        return None


class _RichLikeHandler(logging.Handler):
    """Stands in for the MCP SDK's rich console handler, recognised by name."""

    def emit(self, record: logging.LogRecord) -> None:
        return None


_RichLikeHandler.__name__ = "RichHandler"


@pytest.fixture()
def bare_root() -> Iterator[logging.Logger]:
    """A private logger standing in for the root: no handlers, level WARNING."""
    logger = logging.Logger("test-root-stand-in")
    logger.setLevel(logging.WARNING)
    yield logger


def test_exporter_only_root_gains_a_console_handler_at_info(bare_root: logging.Logger) -> None:
    bare_root.addHandler(_ExporterHandler())
    installed = configure_logging("INFO", bare_root)
    assert installed is not None
    assert bare_root.level == logging.INFO
    assert [type(h).__name__ for h in bare_root.handlers] == ["_ExporterHandler", "StreamHandler"]


def test_second_call_adds_nothing(bare_root: logging.Logger) -> None:
    configure_logging("INFO", bare_root)
    assert configure_logging("DEBUG", bare_root) is None
    assert bare_root.level == logging.DEBUG
    assert sum(isinstance(h, logging.StreamHandler) for h in bare_root.handlers) == 1


def test_rich_console_handler_is_not_doubled(bare_root: logging.Logger) -> None:
    bare_root.addHandler(_RichLikeHandler())
    assert configure_logging("INFO", bare_root) is None
    assert len(bare_root.handlers) == 1


def test_level_is_sanitised_and_validated(bare_root: logging.Logger) -> None:
    configure_logging(" warning ", bare_root)
    assert bare_root.level == logging.WARNING
    with pytest.raises(
        ValueError,
        match="level must be one of \\['DEBUG', 'INFO', 'WARNING', 'ERROR'\\]; got 'loud'",
    ):
        configure_logging("loud", bare_root)
