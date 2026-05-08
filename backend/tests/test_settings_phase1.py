"""
Phase 1 settings tests — sub-model defaults, validators, named env aliases.

Each guard clause introduced in Phase 1 has a triggering test that
asserts the error message content, not just that an exception was
raised. The locked architectural decisions (embedding dimension,
escalation rule set) are pinned by tests so a silent drift in the
defaults will fail loudly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.settings import (
    DatabaseSettings,
    EmbeddingSettings,
    EscalationSettings,
    LangfuseSettings,
    Settings,
)


def test_settings_instantiates_with_named_alias() -> None:
    """Named DATABASE_URL alias propagates to database.url."""
    settings = Settings()
    assert settings.database.url.get_secret_value().startswith("postgres")


def test_database_settings_rejects_non_postgres_scheme() -> None:
    with pytest.raises(ValueError) as excinfo:
        DatabaseSettings(url="mysql://example.invalid/db")  # type: ignore[arg-type]
    message = str(excinfo.value)
    assert "must use postgresql:// or postgres:// scheme" in message
    assert "mysql" in message


def test_database_settings_defaults_for_pool_and_timeout() -> None:
    db = DatabaseSettings(url="postgresql://localhost/db")  # type: ignore[arg-type]
    assert db.min_pool_size == 1
    assert db.max_pool_size == 5
    assert db.statement_timeout_ms == 30_000
    assert db.echo_sql is False


def test_llm_settings_defaults_match_locked_models() -> None:
    settings = Settings()
    assert settings.llm.anthropic.orchestrator_model == "claude-sonnet-4-6"
    assert settings.llm.anthropic.doc_parser_model == "claude-haiku-4-5-20251001"
    assert settings.llm.anthropic.guardrail_model == "claude-haiku-4-5-20251001"
    assert settings.llm.mistral.validator_model == "mistral-large-latest"
    assert settings.llm.mistral.adjuster_model == "mistral-large-latest"


def test_embedding_dimension_is_locked_to_384() -> None:
    with pytest.raises(ValueError) as excinfo:
        EmbeddingSettings(dimension=512)
    message = str(excinfo.value)
    assert "locked to 384" in message
    assert "BAAI/bge-small-en-v1.5" in message


def test_embedding_settings_defaults() -> None:
    e = EmbeddingSettings()
    assert e.model_name == "BAAI/bge-small-en-v1.5"
    assert e.dimension == 384
    assert e.normalise_embeddings is True
    assert e.batch_size == 32


def test_langfuse_disabled_by_default() -> None:
    lf = LangfuseSettings()
    assert lf.enabled is False
    assert lf.public_key is None
    assert lf.secret_key is None


def test_langfuse_enabled_requires_both_keys() -> None:
    with pytest.raises(ValueError) as excinfo:
        LangfuseSettings(enabled=True, public_key="pk_x")  # type: ignore[arg-type]
    message = str(excinfo.value)
    assert "credentials are incomplete" in message
    assert "public_key set=True" in message
    assert "secret_key set=False" in message


def test_escalation_defaults_match_locked_rules() -> None:
    e = EscalationSettings()
    assert e.auto_approve_ceiling == Decimal("250000")
    assert e.validator_confidence_floor == 0.65
    assert e.adjuster_confidence_floor == 0.75
    assert sorted(e.hard_rules) == sorted(
        [
            "guardrail_failed",
            "claim_type_watchlist",
            "claimant_watchlist",
            "cross_jurisdictional",
        ]
    )


def test_escalation_floors_clamp_to_unit_interval() -> None:
    with pytest.raises(ValueError):
        EscalationSettings(validator_confidence_floor=1.5)
    with pytest.raises(ValueError):
        EscalationSettings(adjuster_confidence_floor=-0.1)


def test_extra_keys_rejected_at_top_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """`extra='forbid'` at the top level prevents a typo'd YAML key from
    silently being ignored."""
    # Construct via kwargs so we exercise the same forbid path the YAML
    # overlay flows through.
    with pytest.raises(ValueError):
        Settings(unknown_top_level_key=1)  # type: ignore[call-arg]
