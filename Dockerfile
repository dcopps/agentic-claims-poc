# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Backend image for Azure Container Apps (Phase 9.1).
#
# Strategy: a two-stage build. The builder resolves the locked dependency set
# with uv, installs the project and downloads the embedding model into a cache
# directory inside the image. The runtime stage copies only the virtualenv, the
# source tree and that model cache, and runs as a non-root user with Hugging
# Face access switched OFF — so the model the container serves is exactly the
# one baked at build time, and a missing model fails loudly instead of being
# fetched from a third-party endpoint at demo time.
#
# Built with `az acr build` (never local Docker — decided 21 September 2026);
# see infra/bicep/README.md. The build context is governed by .dockerignore.
# ---------------------------------------------------------------------------

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
# Pinned to the uv version used on the developer machine so lockfile semantics
# are identical in both places.
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.9.11

# ----------------------------- builder -------------------------------------
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /usr/local/bin/uv

# Compile bytecode at install time (faster cold start); copy rather than
# hard-link across layers; never let uv download its own interpreter — the
# base image's 3.11 is the one the lockfile was resolved for.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first, cached independently of application source. README.md
# is needed because hatchling reads it for package metadata.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source, then the project itself (editable, so there is a single
# copy of the repo-relative data files the app reads: policy.yaml,
# variants.yaml, sample_policy.txt, prompts). importlib.metadata reports the
# pyproject version, which is what /health returns.
COPY backend/ backend/
RUN uv sync --frozen --no-dev

# Bake the embedding model. The literal model id must equal
# `EmbeddingSettings.model_name` in backend/settings.py (the two are interlocked
# like the model name and vector dimension already are). Reading it from
# Settings here would require a DATABASE_URL at build time — the wrong coupling.
ENV HF_HOME=/opt/hf
RUN /app/.venv/bin/python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('BAAI/bge-small-en-v1.5')"

# ----------------------------- runtime -------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# Non-root service account; no home directory, no shell login.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
COPY --from=builder --chown=app:app /opt/hf /opt/hf

# HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE make "no runtime egress to Hugging Face"
# enforced rather than incidental: the libraries refuse to open a network
# connection and raise if the baked cache is incomplete.
ENV HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

USER app

# Container Apps configures the ingress targetPort rather than injecting $PORT
# (as Render does), so the port is fixed here. 8000 is Settings.api_port's
# default; the Bicep `targetPort` must match.
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
