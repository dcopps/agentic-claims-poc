"""
Anonymisation regression guard.

The prototype is generic: the client's name must not appear anywhere in the
committed repository. The actual client name has been kept out throughout, so it
is unknown to this build; this test greps the working tree for a list of
*candidate* regulated/specialty-insurer identifiers (the plausible names earlier
phases grepped for) and fails if any appears. Expected result: zero matches.

The architect performs a one-time manual grep of the real client name before any
public push; this test is the standing regression guard. To extend it, add the
real name to `_FORBIDDEN` (it is already absent).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories scanned (relative to repo root) plus a few top-level files.
_SCAN_ROOTS = ("backend", "frontend/src", "docs", "infra", "scripts", "diagrams")
_SCAN_FILES = ("README.md", "CLAUDE.md")

# Directory names skipped anywhere in the tree. `learning` excludes the
# uncommitted personal `docs/learning/`; the rest are generated / vendored.
_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "learning",
}

_TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml",
    ".json", ".txt", ".sh", ".toml", ".css", ".html", ".mmd",
}

# The build's meta-record — excluded because it legitimately documents the
# anonymisation grep methodology (the candidate patterns themselves). These are
# path-specific so `backend/app/prompts/` (real deliverables) is still scanned.
_EXCLUDE_RELPATHS = ("docs/prompts/", "docs/build-log.md")

# This file deliberately contains the candidate names, so it is excluded.
_SELF = Path(__file__).resolve()

# Candidate forbidden identifiers — plausible regulated/specialty insurers. Word
# boundaries avoid innocent substring hits. The list is candidate-based, not the
# real client name (which is already absent).
_FORBIDDEN: tuple[str, ...] = (
    r"\baspen\b",
    r"\baxa\b",
    r"\bchubb\b",
    r"\bswiss\s+re\b",
    r"\bmunich\s+re\b",
    r"\bhiscox\b",
    r"\bbeazley\b",
    r"\blancashire\b",
    r"\bargo\s+group\b",
)


def _scannable_files() -> list[Path]:
    files: list[Path] = []
    for name in _SCAN_FILES:
        path = _REPO_ROOT / name
        if path.is_file():
            files.append(path)
    for root in _SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if any(part in _EXCLUDE_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
                continue
            if path.resolve() == _SELF:
                continue
            rel = str(path.relative_to(_REPO_ROOT))
            if any(rel == ex or rel.startswith(ex) for ex in _EXCLUDE_RELPATHS):
                continue
            files.append(path)
    return files


# Gather once; each parametrised case searches the shared corpus.
_CORPUS: list[tuple[Path, str]] = [
    (path, path.read_text(encoding="utf-8", errors="replace")) for path in _scannable_files()
]


@pytest.mark.parametrize("pattern", _FORBIDDEN)
def test_no_forbidden_identifier(pattern: str) -> None:
    regex = re.compile(pattern, re.IGNORECASE)
    hits = [
        str(path.relative_to(_REPO_ROOT))
        for path, text in _CORPUS
        if regex.search(text)
    ]
    assert hits == [], (
        f"anonymisation: forbidden identifier /{pattern}/ found in {hits}"
    )


def test_corpus_is_non_empty() -> None:
    # Guards against the scan silently matching nothing because the roots moved.
    assert len(_CORPUS) > 20
