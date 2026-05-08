"""
index_policy tests — chunker (always run) plus an optional end-to-end
embedding test gated by `RUN_EMBEDDING_TESTS=1`.

The chunker is exercised against the real policy file. Token counts
are produced via the embedding tokenizer at test time so the assertions
hold against whatever tokeniser the locked model ships.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from backend.data.index_policy import (
    _TARGET_TOKENS_MAX,
    _TARGET_TOKENS_MIN,
    chunk_markdown_sections,
)

_POLICY_PATH = Path("backend/data/sample_policy.txt")


@pytest.fixture(scope="module")
def tokenizer() -> Any:
    """Load the bge-small tokenizer once per module run.

    Returns `Any` because `transformers`' tokenizer hierarchy uses dynamic
    `from_pretrained` factories whose precise return type isn't worth
    pinning in test code.
    """
    pytest.importorskip("transformers")
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")


def test_policy_file_exists() -> None:
    assert _POLICY_PATH.exists(), f"sample policy missing at {_POLICY_PATH}"


def test_chunker_produces_at_least_one_chunk_per_section(tokenizer: Any) -> None:
    text = _POLICY_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown_sections(text, str(_POLICY_PATH), tokenizer)

    expected_sections = {
        "General Conditions",
        "Definitions",
        "Named Perils Covered",
        "Exclusions",
        "Sub-Limits",
        "Business Interruption",
        "Duties After Loss",
    }
    seen_sections = {c.section for c in chunks}
    assert expected_sections <= seen_sections


def test_chunks_have_strictly_positive_token_counts(tokenizer: Any) -> None:
    text = _POLICY_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown_sections(text, str(_POLICY_PATH), tokenizer)
    for c in chunks:
        assert c.token_count > 0


def test_no_chunk_exceeds_target_max_too_far(tokenizer: Any) -> None:
    """
    Chunks may slightly exceed `_TARGET_TOKENS_MAX` because the packer
    only stops adding *additional* paragraphs once max is breached — a
    single oversized paragraph still emits as its own chunk. We allow
    a 50% overshoot beyond max as the practical envelope.
    """
    text = _POLICY_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown_sections(text, str(_POLICY_PATH), tokenizer)
    practical_cap = _TARGET_TOKENS_MAX + (_TARGET_TOKENS_MAX // 2)
    for c in chunks:
        assert c.token_count <= practical_cap


def test_chunker_indexes_are_sequential(tokenizer: Any) -> None:
    text = _POLICY_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown_sections(text, str(_POLICY_PATH), tokenizer)
    for expected, chunk in enumerate(chunks):
        assert chunk.chunk_index == expected


def test_chunker_rejects_empty_text(tokenizer: Any) -> None:
    with pytest.raises(ValueError) as excinfo:
        chunk_markdown_sections("", "x.txt", tokenizer)
    assert "empty text" in str(excinfo.value)


def test_chunker_rejects_text_without_headings(tokenizer: Any) -> None:
    with pytest.raises(ValueError) as excinfo:
        chunk_markdown_sections("just a paragraph", "x.txt", tokenizer)
    assert "section-delimited" in str(excinfo.value)


def test_chunker_rejects_inverted_target_range(tokenizer: Any) -> None:
    with pytest.raises(ValueError) as excinfo:
        chunk_markdown_sections(
            "# A\n\nbody",
            "x.txt",
            tokenizer,
            target_min=_TARGET_TOKENS_MAX,
            target_max=_TARGET_TOKENS_MIN,
        )
    assert "target_min must be <= target_max" in str(excinfo.value)


@pytest.mark.skipif(
    os.environ.get("RUN_EMBEDDING_TESTS") != "1",
    reason="end-to-end embedding test is opt-in (RUN_EMBEDDING_TESTS=1)",
)
def test_end_to_end_index_run() -> None:
    """Loads the model and runs the full indexing pipeline against the DB."""
    from backend.data.index_policy import main

    rc = main()
    assert rc == 0
