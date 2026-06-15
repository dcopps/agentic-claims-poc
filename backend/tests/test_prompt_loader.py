"""
Tests for `backend.app.prompts.PromptLoader`.

Every guard in `_load` and `_read_prompt_file` has a triggering test.
Real prompt files (`system/validator.md`, `user/validator_template.md`)
exercise the happy path; per-test temporary trees exercise the error
paths so the canonical prompts stay clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.prompts import (
    PromptFormatError,
    PromptLoader,
    PromptNotFoundError,
)
from backend.app.prompts.loader import _MAX_PROMPT_BYTES


@pytest.fixture()
def temp_prompt_root(tmp_path: Path) -> Path:
    """Create a `system/` + `user/` tree inside a tmp directory."""
    (tmp_path / "system").mkdir()
    (tmp_path / "user").mkdir()
    return tmp_path


def test_loads_real_system_prompt(prompt_loader: PromptLoader) -> None:
    text = prompt_loader.system("validator")
    assert text.startswith("# Role")
    assert "coverage validator" in text


def test_loads_real_user_template(prompt_loader: PromptLoader) -> None:
    rendered = prompt_loader.user(
        "validator_template",
        claim_narrative="example narrative",
        retrieved_chunks="[chunk_id=abc] example chunk",
    )
    assert "example narrative" in rendered
    assert "[chunk_id=abc] example chunk" in rendered


# Note: the Phase 8.1 `test_doc_parser_prompt_covers_hedged_dollar_figures`
# regression test was removed in Phase 8.2. It pinned a few-shot dollar-extraction
# block into the doc_parser prompt — the very approach Phase 8.2 abandons. The
# structured fields (including the amount) now come from the claim record, and the
# prompt asks Haiku only for a plain-prose summary, so there is no extraction block
# left to guard. The summariser-prompt shape is covered by
# `test_doc_parser_prompts.py::test_system_prompt_declares_summary_role_and_output_shape`.


def test_missing_file_raises_prompt_not_found(temp_prompt_root: Path) -> None:
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(PromptNotFoundError) as exc_info:
        loader.system("nonexistent")
    assert "nonexistent" in str(exc_info.value)


def test_empty_file_raises_value_error(temp_prompt_root: Path) -> None:
    (temp_prompt_root / "system" / "empty.md").write_text("")
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(ValueError) as exc_info:
        loader.system("empty")
    assert "empty" in str(exc_info.value).lower()


def test_oversized_file_raises_value_error(temp_prompt_root: Path) -> None:
    (temp_prompt_root / "system" / "big.md").write_bytes(
        b"x" * (_MAX_PROMPT_BYTES + 1)
    )
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(ValueError) as exc_info:
        loader.system("big")
    assert "exceeds the size cap" in str(exc_info.value)


def test_path_traversal_name_rejected(temp_prompt_root: Path) -> None:
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(PromptFormatError) as exc_info:
        loader.system("../etc/passwd")
    assert "[A-Za-z0-9_-]+" in str(exc_info.value)


def test_blank_name_rejected(temp_prompt_root: Path) -> None:
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(PromptFormatError) as exc_info:
        loader.system("   ")
    assert "non-empty" in str(exc_info.value)


def test_user_template_missing_placeholder_raises(temp_prompt_root: Path) -> None:
    (temp_prompt_root / "user" / "needs_two.md").write_text("Hello {a} and {b}")
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(PromptFormatError) as exc_info:
        loader.user("needs_two", a="A")
    assert "'b'" in str(exc_info.value)
    assert "needs_two" in str(exc_info.value)


def test_user_template_extra_placeholders_ignored(temp_prompt_root: Path) -> None:
    (temp_prompt_root / "user" / "one.md").write_text("Hello {a}")
    loader = PromptLoader(base_path=temp_prompt_root)
    rendered = loader.user("one", a="A", b="ignored")
    assert rendered == "Hello A"


def test_clear_cache_picks_up_edits(temp_prompt_root: Path) -> None:
    target = temp_prompt_root / "system" / "drifting.md"
    target.write_text("first")
    loader = PromptLoader(base_path=temp_prompt_root)
    assert loader.system("drifting") == "first"

    target.write_text("second")
    # Without clearing, the cache returns the first read.
    assert loader.system("drifting") == "first"
    PromptLoader.clear_cache()
    assert loader.system("drifting") == "second"


def test_base_path_must_be_directory(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "not-a-dir.txt"
    not_a_dir.write_text("x")
    with pytest.raises(ValueError) as exc_info:
        PromptLoader(base_path=not_a_dir)
    assert "existing directory" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Phase 6 — raw() unformatted reads
# --------------------------------------------------------------------------- #


def test_raw_user_returns_unformatted_template() -> None:
    """raw() returns the template with placeholders intact (not substituted)."""
    loader = PromptLoader()
    content = loader.raw("user", "validator_template")
    assert "{claim_narrative}" in content
    assert "{retrieved_chunks}" in content


def test_raw_system_returns_verbatim() -> None:
    loader = PromptLoader()
    content = loader.raw("system", "validator")
    assert "coverage validator" in content


def test_raw_rejects_unknown_kind() -> None:
    loader = PromptLoader()
    with pytest.raises(PromptFormatError) as exc:
        loader.raw("instructions", "validator")
    assert "kind must be one of" in str(exc.value)


def test_raw_missing_file_raises(temp_prompt_root: Path) -> None:
    loader = PromptLoader(base_path=temp_prompt_root)
    with pytest.raises(PromptNotFoundError):
        loader.raw("user", "does_not_exist")


def test_raw_rejects_path_traversal() -> None:
    loader = PromptLoader()
    with pytest.raises(PromptFormatError) as exc:
        loader.raw("user", "../system/validator")
    assert "must match" in str(exc.value)
