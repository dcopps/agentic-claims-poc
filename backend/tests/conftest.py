"""
Shared pytest fixtures.

Phase 0 contributed `client` (a `TestClient` over a fresh FastAPI app);
Phase 1 added three database-backed fixtures (`db_settings`,
`migrated_db`, `clean_db`).

Phase 2 adds Validator-side fixtures:

  - `prompt_loader` (function-scoped) — a fresh `PromptLoader` rooted at
    `backend/app/prompts/`; cache cleared per test.
  - `stub_embedder` (function-scoped) — a callable that produces a
    deterministic 384-dim unit vector. Used by Validator unit tests so
    they do not pay the SentenceTransformer cold-load cost.
  - `mock_provider` (function-scoped) — a stub `LLMProvider` whose
    `complete()` returns a configurable `ProviderResponse`. Captures
    the call arguments for assertion.
  - `null_api_logger` (function-scoped) — an `APILogger` whose sink
    discards every record. Used wherever a provider needs *some*
    logger but the test does not care about log output.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import numpy as np
import psycopg
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from backend.app.llm.provider import (
    LLMProvider,
    ProviderResponse,
    ResponseFormat,
)
from backend.app.logging.api_logger import APIAgentName, APILogger
from backend.app.main import create_app
from backend.app.prompts import PromptLoader
from backend.db.connection import open_connection
from backend.settings import Settings


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient bound to a fresh app instance per test."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# Test-database safety (Phase 8.5)
#
# The suite's destructive fixtures TRUNCATE tables. If the resolved database is
# the deployed Neon instance, running pytest wipes production — which is exactly
# what happened in Phase 8.4. The helpers below pin the suite to a *non-Neon*
# database and refuse, loudly, to do anything else.
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_PATH = _REPO_ROOT / ".env"
_DOTENV_TEST_PATH = _REPO_ROOT / ".env.test"

# Managed-Neon hosts all live under this suffix. The categorical rule is: the
# test suite never targets one, with no env-var bypass.
_NEON_HOST_SUFFIX = ".neon.tech"

# Every refusal points the developer at the one place that explains the fix.
_README_POINTER = (
    "See the 'Local test database setup' section of README.md: create a local "
    "test database (DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh) "
    "and set TEST_DATABASE_URL in .env.test to it — never a .neon.tech host."
)


def _is_neon_host(url: str) -> bool:
    """True if `url`'s host is a managed-Neon host (`*.neon.tech`), case-insensitive."""
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(_NEON_HOST_SUFFIX)


def _resolve_test_database_url(test_url: str | None, database_url: str | None) -> str:
    """
    Resolve the database URL the suite may safely TRUNCATE, or raise `RuntimeError`.

    Categorical safety rule: never a Neon (`*.neon.tech`) host. Prefer an explicit
    `TEST_DATABASE_URL`; fall back to `DATABASE_URL` only when it is itself non-Neon
    (the CI path, where `DATABASE_URL` is a localhost service container).

    Defensive ordering: sanitise (strip) → validate (presence + host) → abort
    (raise with the offending host) → execute (return the safe URL). No silent
    fallback, no opt-in bypass.
    """
    test_url = (test_url or "").strip()
    database_url = (database_url or "").strip()

    if test_url:
        # An explicit test URL pointing at Neon is always a configuration error.
        if _is_neon_host(test_url):
            raise RuntimeError(
                "TEST_DATABASE_URL points at a Neon host "
                f"({urlparse(test_url).hostname!r}); the test suite TRUNCATEs tables "
                f"and must never run against deployed data. {_README_POINTER}"
            )
        return test_url

    if database_url:
        # CI sets DATABASE_URL to a localhost Postgres and no TEST_DATABASE_URL;
        # accept it only because it is non-Neon. A Neon DATABASE_URL with no
        # TEST_DATABASE_URL is the laptop foot-gun this whole change exists to stop.
        if _is_neon_host(database_url):
            raise RuntimeError(
                "No TEST_DATABASE_URL is set and DATABASE_URL points at a Neon host "
                f"({urlparse(database_url).hostname!r}); refusing to run destructive "
                f"tests against deployed data. {_README_POINTER}"
            )
        return database_url

    raise RuntimeError(
        "No test database configured: both TEST_DATABASE_URL and DATABASE_URL are "
        f"unset. {_README_POINTER}"
    )


def _read_env_candidate(name: str, dotenv_path: Path) -> str | None:
    """
    Read `name` from `os.environ`, falling back to `dotenv_path` if present.

    Mirrors `Settings`' precedence — a real environment variable wins over the
    dotenv file, so CI's exported `DATABASE_URL` is authoritative.
    """
    value = os.environ.get(name)
    if value:
        return value
    if dotenv_path.exists():
        return dotenv_values(dotenv_path).get(name)
    return None


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    """
    Resolve Settings once per session, pinned to a *safe* (non-Neon) database.

    `_resolve_test_database_url` enforces the safety rule and raises loudly on any
    Neon target rather than letting `clean_db` TRUNCATE it. The resolved URL is
    injected via `os.environ["DATABASE_URL"]` — the highest-precedence path
    `Settings` honours — so every `Settings()` / `open_connection()` built during
    the session, explicit or bare, targets the test database.
    """
    test_url = _read_env_candidate("TEST_DATABASE_URL", _DOTENV_TEST_PATH)
    database_url = _read_env_candidate("DATABASE_URL", _DOTENV_PATH)
    resolved = _resolve_test_database_url(test_url, database_url)

    os.environ["DATABASE_URL"] = resolved
    return Settings()


@pytest.fixture(scope="session")
def migrated_db(db_settings: Settings) -> Settings:
    """
    Ensure migrations are applied to the configured database.

    Runs `alembic upgrade head` from the repo root. Idempotent: a
    repeat run is a no-op because Alembic stamps `alembic_version`.
    """
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    # Propagate the resolved DATABASE_URL so Alembic's env.py picks up
    # the same value Settings did (matters when Settings sourced it from
    # `.env` rather than the shell).
    env["DATABASE_URL"] = db_settings.database.url.get_secret_value()

    result = subprocess.run(
        ["uv", "run", "alembic", "--config", "backend/alembic.ini", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed during test session setup; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return db_settings


@pytest.fixture()
def clean_db(migrated_db: Settings) -> Iterator[psycopg.Connection]:
    """
    Yield a fresh connection with all Phase 1 tables truncated.

    `RESTART IDENTITY` resets the `audit_log.audit_id` sequence so
    chain-hash assertions across tests aren't sensitive to the order
    pytest happens to pick.
    """
    # Defence in depth: `db_settings` already refuses a Neon target, but a
    # destructive TRUNCATE is the wrong place to trust an upstream invariant.
    # Re-check the resolved host here so no future fixture wiring can route this
    # fixture at deployed data without tripping the guard.
    url = migrated_db.database.url.get_secret_value()
    if _is_neon_host(url):
        raise RuntimeError(
            "clean_db refuses to TRUNCATE a Neon host "
            f"({urlparse(url).hostname!r}). {_README_POINTER}"
        )
    with open_connection(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE policy_chunks, audit_log, claims "
                "RESTART IDENTITY CASCADE"
            )
        conn.commit()
        yield conn


# --------------------------------------------------------------------------- #
# Phase 2 fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def prompt_loader() -> PromptLoader:
    """A fresh PromptLoader with the file-content cache cleared."""
    PromptLoader.clear_cache()
    return PromptLoader()


@pytest.fixture()
def stub_embedder() -> Callable[[str], np.ndarray]:
    """
    Return a deterministic 384-dim embedder.

    The vector is derived from the hash of the input so two distinct
    narratives produce distinct vectors, but the values are stable
    across runs. Normalised to unit length so similarity arithmetic
    behaves like the real bge-small encoder.
    """

    def embed(text: str) -> np.ndarray:
        # Seed from the text so distinct inputs are distinguishable but
        # repeatable. Python's hash() is salted per-process, so use a
        # stable hash over the encoded bytes instead.
        import hashlib

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Stretch the 32-byte digest to 384 floats by repeating + jitter.
        repeated = (digest * 12)[:384]
        vector = np.frombuffer(repeated, dtype=np.uint8).astype(np.float32)
        vector = vector - 127.5
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            raise AssertionError(
                "stub_embedder: zero-norm vector — change the input"
            )
        return (vector / norm).astype(np.float32)

    return embed


@dataclass
class MockProviderCall:
    """One captured `LLMProvider.complete()` call's arguments."""

    system: str
    user: str
    model: str
    max_tokens: int
    temperature: float
    correlation_id: UUID
    agent: APIAgentName
    step: str
    response_format: ResponseFormat
    timeout_s: float


@dataclass
class MockProvider(LLMProvider):
    """Test double for `LLMProvider`."""

    vendor: str = "mock"
    response_text: str = "{}"
    response_model: str = "mock-model-latest"
    prompt_tokens: int = 100
    completion_tokens: int = 50
    latency_ms: int = 10
    raise_on_call: BaseException | None = None
    calls: list[MockProviderCall] = field(default_factory=list)

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
        correlation_id: UUID,
        agent: APIAgentName,
        step: str,
        response_format: ResponseFormat = "text",
        timeout_s: float = 60.0,
    ) -> ProviderResponse:
        self.calls.append(
            MockProviderCall(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                correlation_id=correlation_id,
                agent=agent,
                step=step,
                response_format=response_format,
                timeout_s=timeout_s,
            )
        )
        if self.raise_on_call is not None:
            raise self.raise_on_call
        total = self.prompt_tokens + self.completion_tokens
        return ProviderResponse(
            text=self.response_text,
            model=self.response_model,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=total,
            latency_ms=self.latency_ms,
        )


@pytest.fixture()
def mock_provider() -> MockProvider:
    """A fresh `MockProvider` per test."""
    return MockProvider()


@pytest.fixture()
def null_api_logger() -> APILogger:
    """An APILogger whose sink discards every record."""
    return APILogger(enabled=True, excerpt_chars=200, sink=lambda _line: None)
