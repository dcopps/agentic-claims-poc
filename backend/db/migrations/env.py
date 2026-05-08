"""
Alembic migration environment.

Reads `DATABASE_URL` from `Settings` so migrations and the runtime app
share configuration. There is no SQLAlchemy `MetaData` declared here
because the project doesn't use the ORM — migrations issue raw SQL via
`op.execute(...)`. `target_metadata` is therefore `None`, which disables
autogeneration (we don't want it; every migration is hand-written).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.settings import Settings

config = context.config

# Inject the runtime DATABASE_URL into Alembic's config. We read it from
# Settings rather than from `alembic.ini` so the same env-var-or-yaml
# resolution that drives the app drives migrations as well.
#
# SQLAlchemy needs to know which DBAPI to load. The application uses
# `psycopg` (v3, "psycopg") and we have NOT installed `psycopg2`. Rewrite
# the URL scheme to the explicit `postgresql+psycopg://` form so
# SQLAlchemy picks the right driver instead of defaulting to psycopg2.
_settings = Settings()
_raw_url = _settings.database.url.get_secret_value()
if _raw_url.startswith("postgresql://"):
    _alembic_url = "postgresql+psycopg://" + _raw_url[len("postgresql://"):]
elif _raw_url.startswith("postgres://"):
    _alembic_url = "postgresql+psycopg://" + _raw_url[len("postgres://"):]
else:
    _alembic_url = _raw_url
config.set_main_option("sqlalchemy.url", _alembic_url)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without an Engine — emits SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
