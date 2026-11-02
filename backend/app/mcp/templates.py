"""
The two MCP prompts and the one resource.

A prompt is a template the client offers its user: it tells the model which
tools to call in which order and what to report. Both live as externalised
files under `backend/app/prompts/user/` and are read through `PromptLoader`,
like every other prompt in the system, so they can be reviewed as prose and
a missing placeholder fails loudly.

The resource is the policy excerpt the Validator searches, so an answer can
quote the wording a passage came from.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server import MCPServer

from backend.app.prompts import PromptLoader
from backend.settings import Settings

# The largest policy text this prototype will serve as a resource. The excerpt
# is a few kilobytes; a file past this bound is the wrong file.
_MAX_POLICY_BYTES = 256 * 1024


def register_templates(server: MCPServer, settings: Settings) -> None:
    """Attach the two prompts and the policy resource to `server`."""
    loader = PromptLoader()
    policy_path = settings.retrieval.policy_source_path

    @server.prompt(
        name="audit_this_run",
        title="Audit this run",
        description="Verify the chain, explain the run, and report it row by row.",
    )
    def audit_this_run(correlation_id: str) -> str:
        return loader.user("mcp_audit_this_run", correlation_id=correlation_id.strip())

    @server.prompt(
        name="why_settled_or_escalated",
        title="Why did this claim settle or escalate?",
        description="Explain a claim's latest run in plain language, citing the rows.",
    )
    def why_settled_or_escalated(claim_id: str) -> str:
        return loader.user("mcp_why_settled_or_escalated", claim_id=claim_id.strip())

    @server.resource(
        "policy://excerpt",
        name="policy_excerpt",
        title="The policy excerpt",
        description="The commercial property policy wording the Validator searches.",
        mime_type="text/plain",
    )
    def policy_excerpt() -> str:
        return read_policy_excerpt(policy_path)


def read_policy_excerpt(path: Path) -> str:
    """Read the policy text, refusing a missing, empty or oversized file."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"policy excerpt not found at {resolved}")
    size = resolved.stat().st_size
    if size == 0 or size > _MAX_POLICY_BYTES:
        raise ValueError(
            f"policy excerpt at {resolved} is {size} bytes; expected 1..{_MAX_POLICY_BYTES}"
        )
    return resolved.read_text(encoding="utf-8")
