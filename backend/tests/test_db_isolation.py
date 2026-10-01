"""
Phase 8.5 — discriminator tests for the test-database safety guard.

These prove the categorical rule that the suite never resolves to a deployed
database host: managed Neon (Phase 8.5) or Azure Database for PostgreSQL
Flexible Server (Phase 9.1). They exercise the pure resolver
`_resolve_test_database_url` directly with controlled inputs, so they need
**no database** and have **no side effects** — which is the whole point: the
safety property must be verifiable without risking the very wipe it prevents.

If anyone reverts the guard, or narrows it back to Neon only, these fail.
"""

from __future__ import annotations

import pytest

from .conftest import _resolve_test_database_url

_NEON_URL = "postgresql://u:p@ep-misty-dream-alif9suz.c-3.eu-central-1.aws.neon.tech/db"
_NEON_HOST = "ep-misty-dream-alif9suz.c-3.eu-central-1.aws.neon.tech"
_LOCAL_URL = "postgresql://dev@localhost:5432/agentic_claims_test"
# The Phase 9.1 Azure data tier. Shape matches a real Flexible Server FQDN; the
# server name is invented.
_AZURE_HOST = "psql-claimsai-dev-abcde.postgres.database.azure.com"
_AZURE_URL = f"postgresql://claimsadmin:p@{_AZURE_HOST}:5432/agentic_claims?sslmode=require"


def test_guard_fires_on_neon_test_url() -> None:
    """An explicit TEST_DATABASE_URL pointing at Neon raises, naming the host.

    Case-insensitivity is asserted too: the host suffix match must not be
    defeatable by upper-casing the URL.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _resolve_test_database_url(_NEON_URL, None)
    message = str(exc_info.value)
    assert "TEST_DATABASE_URL" in message
    assert _NEON_HOST in message
    # The diagnostic must route the developer to the fix, not just refuse.
    assert "README.md" in message

    # The guard keys on the host suffix, not exact case.
    with pytest.raises(RuntimeError):
        _resolve_test_database_url(_NEON_URL.upper(), None)


def test_guard_allows_local_url() -> None:
    """A localhost URL is returned unchanged via both resolution paths.

    - TEST_DATABASE_URL local wins even when DATABASE_URL is Neon (explicit
      override takes precedence over the foot-gun).
    - The CI shape — no TEST_DATABASE_URL, localhost DATABASE_URL — is accepted.
    """
    assert _resolve_test_database_url(_LOCAL_URL, _NEON_URL) == _LOCAL_URL
    assert _resolve_test_database_url(None, _LOCAL_URL) == _LOCAL_URL


def test_missing_or_neon_only_config_raises_with_pointer() -> None:
    """Both unset, and Neon-only DATABASE_URL with no test URL, both raise loudly."""
    # Case A: nothing configured at all.
    with pytest.raises(RuntimeError) as both_unset:
        _resolve_test_database_url(None, None)
    assert "README.md" in str(both_unset.value)

    # Case B: the laptop foot-gun — no TEST_DATABASE_URL, DATABASE_URL is Neon.
    with pytest.raises(RuntimeError) as neon_fallback:
        _resolve_test_database_url(None, _NEON_URL)
    message = str(neon_fallback.value)
    assert _NEON_HOST in message
    assert "README.md" in message


def test_guard_fires_on_azure_test_url() -> None:
    """An explicit TEST_DATABASE_URL pointing at Azure Flexible Server raises, naming the host.

    Phase 9.1 discriminator: with `_DEPLOYED_HOST_SUFFIXES` narrowed back to Neon
    only, this URL would be *returned* as safe and the suite would TRUNCATE the
    Azure database. The upper-cased variant proves the suffix match is not
    case-sensitive, as for Neon.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _resolve_test_database_url(_AZURE_URL, None)
    message = str(exc_info.value)
    assert "TEST_DATABASE_URL" in message
    assert _AZURE_HOST in message
    assert "deployed-database host" in message
    assert "README.md" in message

    with pytest.raises(RuntimeError):
        _resolve_test_database_url(_AZURE_URL.upper(), None)


def test_guard_fires_on_azure_database_url_fallback() -> None:
    """The laptop foot-gun, Azure edition: no TEST_DATABASE_URL, DATABASE_URL is Azure.

    This is the exact shape of a shell that just ran the Phase 9.1 bootstrap
    (`export DATABASE_URL=...azure...`) and then ran pytest.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _resolve_test_database_url(None, _AZURE_URL)
    message = str(exc_info.value)
    assert "DATABASE_URL" in message
    assert _AZURE_HOST in message
    assert "README.md" in message

    # And the explicit local override still wins over an Azure DATABASE_URL.
    assert _resolve_test_database_url(_LOCAL_URL, _AZURE_URL) == _LOCAL_URL
