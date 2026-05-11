"""
Settings model — single source of truth for runtime configuration.

Strategy: defaults live in the Pydantic models below. A YAML overlay (loaded
from `backend/settings.yaml` if present) supplies environment-specific
overrides. Environment variables override both, with three named aliases
(`DATABASE_URL`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`) propagated into
their nested sub-model fields ahead of the standard nested-form syntax
(`DATABASE__URL` etc.) — the named aliases keep deployment configuration
ergonomic. CLI flags will layer on top in later phases when there's a CLI
to attach them to.

Phase 0 introduced the flat surface (`app_name`, `environment`, `api_host`,
`api_port`, `log_level`, `cors_allowed_origins`). Phase 1 hangs five
sub-models off `Settings`: `database`, `llm`, `embedding`, `langfuse`,
`escalation`. Their consumers arrive in later phases; the field set here
is exactly what's needed to declare the connection / model identifier.
Per-call parameters (temperature, max_tokens, etc.) are deferred until the
LLM Gateway needs them in Phase 2.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Per-call defaults for the Validator agent. Low temperature keeps the
# coverage decision deterministic across runs; max_tokens is generous
# enough for the JSON verdict plus reasoning paragraph without inviting
# rambling output. Both are configurable via settings.yaml / env.
_DEFAULT_VALIDATOR_MAX_TOKENS = 1024
_DEFAULT_VALIDATOR_TEMPERATURE = 0.1
_DEFAULT_REQUEST_TIMEOUT_S = 60.0

# Bounds for the APILogger's prompt/response excerpt budget. Below 100
# the excerpt is useless; above 20_000 we're effectively logging full
# bodies twice (the audit log already has the full content).
_MIN_LOG_EXCERPT_CHARS = 100
_MAX_LOG_EXCERPT_CHARS = 20_000
_DEFAULT_LOG_EXCERPT_CHARS = 2000

# Default location of the indexed policy excerpt. Mirrors the path used
# by `backend/data/index_policy.py` so retrieval is scoped to the same
# rows the indexer wrote.
_DEFAULT_POLICY_SOURCE_PATH = Path("backend/data/sample_policy.txt")

# Locate the YAML overlay relative to this file. The overlay sits next to
# `settings.py` so a developer who copies the template doesn't need to know
# where the resolution logic looks.
_SETTINGS_YAML_PATH = Path(__file__).parent / "settings.yaml"

# Locate `.env` at the repository root — two levels up from this file
# (`backend/settings.py` -> repo root). `.env` is gitignored; a missing
# file is a legitimate state and yields no overlay.
_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Maximum bytes we'll read from the YAML overlay before refusing. Defensive
# guard against accidentally pointing the path at a huge file.
_MAX_YAML_BYTES = 256 * 1024

# Pinned by the locked architectural decision: the embedding model is
# `BAAI/bge-small-en-v1.5`, which produces 384-dimensional vectors.
# Changing the dimension implies changing the model — a one-way door — so
# the validator below refuses any other value rather than letting a typo
# silently corrupt the index.
_LOCKED_EMBEDDING_DIMENSION = 384

# Locked enumeration of escalation hard rules. Listed once and reused
# as the default for the model field and as the Literal arguments below
# so divergence cannot creep in. The Literal values must match this
# tuple exactly.
HardRule = Literal[
    "guardrail_failed",
    "claim_type_watchlist",
    "claimant_watchlist",
    "cross_jurisdictional",
]

_DEFAULT_HARD_RULES: tuple[HardRule, ...] = (
    "guardrail_failed",
    "claim_type_watchlist",
    "claimant_watchlist",
    "cross_jurisdictional",
)

# Mapping from named env-var alias to the dotted nested-settings path the
# value should populate. Listed once so the propagation loop is data-driven
# and a future addition is a one-line change.
_NAMED_ENV_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DATABASE_URL", ("database", "url")),
    ("ANTHROPIC_API_KEY", ("llm", "anthropic", "api_key")),
    ("MISTRAL_API_KEY", ("llm", "mistral", "api_key")),
)


# --------------------------------------------------------------------------- #
# Sub-models
# --------------------------------------------------------------------------- #


class DatabaseSettings(BaseModel):
    """
    Postgres connection parameters for the prototype's single database.

    `url` carries the full connection string — including the password — and
    is the only field with no default. Instantiation fails fast if it's
    absent so a misconfigured environment surfaces at startup rather than
    silently falling back to a fake URL the agents would later trip on.
    """

    model_config = ConfigDict(extra="forbid")

    url: SecretStr
    min_pool_size: int = Field(default=1, ge=0)
    max_pool_size: int = Field(default=5, ge=1)
    statement_timeout_ms: int = Field(default=30_000, ge=0)
    echo_sql: bool = False

    @field_validator("url")
    @classmethod
    def _validate_scheme(cls, v: SecretStr) -> SecretStr:
        # Reject anything that isn't a Postgres URL up-front. A typo
        # ("postgrss://...") would otherwise propagate to the connection
        # layer and surface as an opaque driver error.
        scheme = v.get_secret_value().split("://", 1)[0]
        if scheme not in {"postgresql", "postgres"}:
            raise ValueError(
                "DatabaseSettings.url must use postgresql:// or postgres:// scheme; "
                f"got scheme={scheme!r}"
            )
        return v


class AnthropicSettings(BaseModel):
    """
    Anthropic provider configuration.

    `api_key` is optional in Phase 1 because no LLM calls happen yet.
    Phase 2 wires the LLM Gateway and re-asserts presence at the call site.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    orchestrator_model: str = "claude-sonnet-4-6"
    doc_parser_model: str = "claude-haiku-4-5-20251001"
    guardrail_model: str = "claude-haiku-4-5-20251001"


class MistralProviderSettings(BaseModel):
    """Mistral provider configuration. See `AnthropicSettings`."""

    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    validator_model: str = "mistral-large-latest"
    adjuster_model: str = "mistral-large-latest"


class LLMSettings(BaseModel):
    """
    Top-level LLM block. Holds one provider sub-block per vendor plus
    the per-call defaults the Gateway hands to every provider.

    `pricing` is the optional rate table the APILogger consults to fill
    `cost_usd`. Keys are model identifiers; values are
    `(input_per_million_tokens, output_per_million_tokens)` in USD. Left
    empty by default — `cost_usd` is null when no rate is configured,
    which is preferable to silently emitting incorrect numbers. Populate
    when the demo's pricing story matters (recommended Phase 6 polish).
    """

    model_config = ConfigDict(extra="forbid")

    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    mistral: MistralProviderSettings = Field(default_factory=MistralProviderSettings)

    # Per-call defaults. The Gateway hands these to every provider unless
    # a caller overrides them. Bounds are tight enough that a typo
    # ("temprature: 5") is rejected at config time.
    validator_max_tokens: int = Field(default=_DEFAULT_VALIDATOR_MAX_TOKENS, ge=1, le=8192)
    validator_temperature: float = Field(
        default=_DEFAULT_VALIDATOR_TEMPERATURE, ge=0.0, le=1.0
    )
    request_timeout_s: float = Field(
        default=_DEFAULT_REQUEST_TIMEOUT_S, ge=1.0, le=600.0
    )

    # Optional pricing table. Decimal so float drift on six-figure
    # token counts can't silently corrupt the cost field. Default empty.
    pricing: dict[str, tuple[Decimal, Decimal]] = Field(default_factory=dict)


class LoggingSettings(BaseModel):
    """
    Structured-log surface for the APILogger.

    The logger writes one JSON record per LLM call. `api_log_enabled`
    gates the whole subsystem (off => silent). `api_log_excerpt_chars`
    caps the prompt/response excerpts so a noisy call does not flood
    the log; the full content already lives in the audit vault.
    `api_log_path` is an optional sidecar file the logger also writes
    to — useful in local development for grepping records without
    scrolling the server log. None means stdout-only.
    """

    model_config = ConfigDict(extra="forbid")

    api_log_enabled: bool = True
    api_log_excerpt_chars: int = Field(
        default=_DEFAULT_LOG_EXCERPT_CHARS,
        ge=_MIN_LOG_EXCERPT_CHARS,
        le=_MAX_LOG_EXCERPT_CHARS,
    )
    api_log_path: Path | None = None


class RetrievalSettings(BaseModel):
    """
    RAG retrieval parameters for the Validator.

    `policy_source_path` filters `policy_chunks` by the row's
    `source_path` column so retrieval is scoped to the corpus the
    indexer wrote. `top_k` defaults to 3 to match the diagram's
    "Cosine similarity search (top 3)" step — overrideable for tuning.
    """

    model_config = ConfigDict(extra="forbid")

    policy_source_path: Path = _DEFAULT_POLICY_SOURCE_PATH
    top_k: int = Field(default=3, ge=1, le=20)


class EmbeddingSettings(BaseModel):
    """
    Embedding model configuration.

    The model name and dimension are interlocked: `bge-small-en-v1.5`
    produces 384-dimensional vectors and the pgvector column is declared
    `VECTOR(384)`. Drifting one without the other yields a silent
    retrieval failure (zeros in the vector, garbage cosine scores). The
    dimension validator pins the value so a typo cannot land in
    `settings.yaml` and corrupt the index.
    """

    model_config = ConfigDict(extra="forbid")

    model_name: str = "BAAI/bge-small-en-v1.5"
    dimension: int = _LOCKED_EMBEDDING_DIMENSION
    normalise_embeddings: bool = True
    batch_size: int = Field(default=32, ge=1)

    @field_validator("dimension")
    @classmethod
    def _pin_to_locked_dimension(cls, v: int) -> int:
        if v != _LOCKED_EMBEDDING_DIMENSION:
            raise ValueError(
                "EmbeddingSettings.dimension is locked to "
                f"{_LOCKED_EMBEDDING_DIMENSION} by the chosen model "
                "(BAAI/bge-small-en-v1.5). Change the model first if you "
                f"need a different dimension; got {v}."
            )
        return v


class LangfuseSettings(BaseModel):
    """
    Langfuse observability configuration.

    Disabled in Phase 1 because no traces are emitted yet. When enabled,
    both keys must be present — half a credential pair would silently fail
    to authenticate, so the validator refuses the configuration up-front.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    host: str = "https://cloud.langfuse.com"

    @model_validator(mode="after")
    def _require_keys_when_enabled(self) -> LangfuseSettings:
        if self.enabled and (self.public_key is None or self.secret_key is None):
            raise ValueError(
                "LangfuseSettings.enabled is True but credentials are incomplete: "
                f"public_key set={self.public_key is not None}, "
                f"secret_key set={self.secret_key is not None}. "
                "Either set both or set enabled=False."
            )
        return self


class EscalationSettings(BaseModel):
    """
    Escalation policy parameters.

    Mirrors the locked decisions in `CLAUDE.md`'s Architectural Decisions
    block exactly: hard rules are always-escalate categories, threshold
    rules trigger when monetary or confidence floors are breached. The
    actual `policy.yaml` file is created by Phase 4; Phase 1 just declares
    the field so the consumer can read it without further plumbing.

    Decimal is used for `auto_approve_ceiling` so monetary comparisons are
    exact — float drift at six-figure values is a real, documented risk.
    """

    model_config = ConfigDict(extra="forbid")

    auto_approve_ceiling: Decimal = Decimal("250000")
    validator_confidence_floor: float = Field(default=0.65, ge=0.0, le=1.0)
    adjuster_confidence_floor: float = Field(default=0.75, ge=0.0, le=1.0)
    hard_rules: list[HardRule] = Field(
        default_factory=lambda: list(_DEFAULT_HARD_RULES)
    )
    policy_path: Path = Path("backend/app/escalation/policy.yaml")


# --------------------------------------------------------------------------- #
# Top-level settings
# --------------------------------------------------------------------------- #


class Settings(BaseSettings):
    """Runtime configuration for the backend."""

    model_config = SettingsConfigDict(
        env_file=None,  # we handle .env manually below to control precedence
        env_nested_delimiter="__",
        extra="forbid",
    )

    # Flat fields (Phase 0 surface area; unchanged).
    app_name: str = Field(default="agentic-claims-poc")
    environment: Literal["dev", "staging", "prod"] = Field(default="dev")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Phase 1 sub-models.
    # `database` uses a default_factory that resolves `DATABASE_URL` from
    # the environment (or `.env`). Declaring a default keeps the type
    # system honest — `Settings()` is callable with no args — without
    # weakening the runtime requirement: a missing URL raises in the
    # factory before construction completes.
    database: DatabaseSettings = Field(default_factory=lambda: _resolve_database_settings())
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    escalation: EscalationSettings = Field(default_factory=EscalationSettings)

    # Phase 2 sub-models.
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)

    @model_validator(mode="before")
    @classmethod
    def _apply_overlays(cls, values: Any) -> Any:
        """
        Merge overlays into the values pydantic-settings has already built.

        Precedence (lowest → highest, last layer wins on conflict):
          1. `settings.yaml` overlay if present.
          2. Values pydantic-settings already collected (init kwargs and
             nested-form env vars like `DATABASE__URL`).
          3. Named env-var aliases (`DATABASE_URL`, `ANTHROPIC_API_KEY`,
             `MISTRAL_API_KEY`) — applied last so the ergonomic deployment
             form trumps the verbose nested form, per the documented rule.
        """
        # Pydantic also passes model instances when revalidating; pass through.
        if not isinstance(values, dict):
            return values

        yaml_overlay = _load_yaml_overrides(_SETTINGS_YAML_PATH)
        named_aliases = _collect_named_env_aliases()

        merged = _deep_merge(yaml_overlay, values)
        merged = _deep_merge(merged, named_aliases)
        return merged


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _load_yaml_overrides(path: Path) -> dict[str, Any]:
    """
    Defensively load YAML overrides from `path`.

    Sanitise → validate → abort → execute:
      1. Sanitise: resolve to an absolute path.
      2. Validate: file exists, is readable, is below the size cap, parses
         as a YAML mapping.
      3. Abort: raise `ValueError` with diagnostic context on any failure.
         No silent fallback — if the file exists but is malformed, the
         caller must know.
      4. Execute: return the parsed mapping (empty dict if the file is
         absent — that's the documented "no overlay" state, not a failure).
    """
    resolved = path.expanduser().resolve()

    # Absent overlay is a legitimate state — defaults stand alone.
    if not resolved.exists():
        return {}

    if not resolved.is_file():
        raise ValueError(
            f"settings.yaml overlay path is not a regular file: {resolved}"
        )

    size = resolved.stat().st_size
    if size > _MAX_YAML_BYTES:
        raise ValueError(
            f"settings.yaml overlay too large: {size} bytes at {resolved} "
            f"(cap is {_MAX_YAML_BYTES} bytes — refusing to load)"
        )

    raw = resolved.read_text(encoding="utf-8")

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        # Surface the parser error with the path so the failure is traceable
        # without re-running. Truncate the YAML body in the message; full
        # content remains in the file on disk.
        excerpt = raw[:500]
        raise ValueError(
            f"settings.yaml overlay at {resolved} is not valid YAML: "
            f"{exc} | first 500 chars: {excerpt!r}"
        ) from exc

    # An empty YAML file parses to None; treat as "no overlay".
    if parsed is None:
        return {}

    if not isinstance(parsed, dict):
        raise ValueError(
            f"settings.yaml overlay at {resolved} must parse to a mapping; "
            f"got {type(parsed).__name__}"
        )

    return parsed


def _resolve_database_settings() -> DatabaseSettings:
    """
    Build `DatabaseSettings` from `DATABASE_URL`.

    Reads from real `os.environ` first; falls back to `.env` if present.
    A missing or empty `DATABASE_URL` raises `ValueError` so misconfigured
    deployments fail at startup with a clear message rather than later
    on the first DB call.
    """
    aliases = _collect_named_env_aliases()
    db_block = aliases.get("database")
    url = db_block.get("url") if isinstance(db_block, dict) else None
    if not url:
        raise ValueError(
            "DATABASE_URL is required (set it in the environment or in .env "
            "at the repository root)"
        )
    return DatabaseSettings(url=url)


def _collect_named_env_aliases() -> dict[str, Any]:
    """
    Resolve the named env aliases (`DATABASE_URL`, `ANTHROPIC_API_KEY`,
    `MISTRAL_API_KEY`) into a nested overlay dict.

    Order of resolution per alias: real `os.environ` wins; if absent, fall
    back to a value from `.env` if that file exists. Missing aliases are
    skipped — the corresponding sub-model field then keeps its default
    (or fails its own required-field check, e.g. `DatabaseSettings.url`).
    """
    env_combined: dict[str, str] = {}
    if _DOTENV_PATH.exists():
        # `dotenv_values` parses without polluting `os.environ` — exactly
        # what we want, since real env vars must take precedence.
        env_combined.update(
            {k: v for k, v in dotenv_values(_DOTENV_PATH).items() if v is not None}
        )
    env_combined.update(os.environ)

    overlay: dict[str, Any] = {}
    for env_name, dotted_path in _NAMED_ENV_ALIASES:
        value = env_combined.get(env_name)
        if value is None or value == "":
            # Empty string is treated as "unset" deliberately — an empty
            # API key is never valid configuration, and it's a common
            # foot-gun in CI where missing secrets render as "".
            continue
        _set_nested(overlay, dotted_path, value)
    return overlay


def _set_nested(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Assign `value` at the dotted-path leaf of `target`, creating dicts as needed."""
    cursor = target
    for key in path[:-1]:
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[path[-1]] = value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge `override` into `base`, returning a new dict.

    Dict-valued keys merge; every other type in `override` replaces the
    corresponding value in `base` outright. The merge is non-destructive
    on the inputs.
    """
    result = dict(base)
    for key, override_value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = _deep_merge(base_value, override_value)
        else:
            result[key] = override_value
    return result
