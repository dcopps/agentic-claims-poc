"""
Structured logging for LLM calls.

`APILogger` writes one canonical-JSON record per LLM call: model,
prompts (truncated), response (truncated), token usage, optional cost
in USD, latency, correlation ID, agent, step, and any error. The
record format is the contract downstream consumers (a future log
explorer, ops dashboards) parse. Field names and types lock at end of
Phase 2.
"""

from backend.app.logging.api_logger import (
    APICallRecord,
    APILogger,
    compute_cost_usd,
)

__all__ = ["APICallRecord", "APILogger", "compute_cost_usd"]
