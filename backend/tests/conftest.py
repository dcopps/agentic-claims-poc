"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient bound to a fresh app instance per test."""
    app = create_app()
    with TestClient(app) as c:
        yield c
