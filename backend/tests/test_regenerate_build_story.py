"""
`scripts/regenerate-build-story.py` over a temporary copy of a small build story.

The script is not a package, so it is loaded from its path. Three behaviours:
identical input → exit 0 and nothing written; a changed TL;DR → exit 1 and
both derived files rewritten; a malformed story → exit 2 with the reason and
nothing written. The real `docs/prompts/README.md` is also checked to be
parseable, so a close-out cannot silently break the command.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "regenerate-build-story.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("regenerate_build_story", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve `from __future__` annotations through sys.modules, so
    # the module must be registered before its body runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_STORY = """# The build

## The build at a glance

| # | Phase | TL;DR |
|---|---|---|
| [01](#entry-01) | Phase 0: a shell | First. |
| [02](#entry-02) | Phase 1: storage | Second. |

## The build, phase by phase

<a name="entry-01"></a>
### 01 — Phase 0: a shell

**TL;DR:** First.

**Technologies:** none.

Body one.

<a name="entry-02"></a>
### 02 — Phase 1: storage

**TL;DR:** Second.

**Technologies:** none.

Body two.
"""

_TLDR = """# The build in thirty seconds a phase

Preamble that must survive.

### [01 — Phase 0: a shell](README.md#entry-01)

First.

### [02 — Phase 1: storage](README.md#entry-02)

Second.

"""


def _write(tmp_path: Path, story: str, tldr: str) -> Path:
    (tmp_path / "README.md").write_text(story, encoding="utf-8")
    (tmp_path / "README_TLDR.md").write_text(tldr, encoding="utf-8")
    return tmp_path / "README.md"


def test_identical_input_exits_zero_and_writes_nothing(tmp_path: Path) -> None:
    story = _write(tmp_path, _STORY, _TLDR)
    before = (story.stat().st_mtime_ns, (tmp_path / "README_TLDR.md").stat().st_mtime_ns)
    assert _load().main(["x", str(story)]) == 0
    after = (story.stat().st_mtime_ns, (tmp_path / "README_TLDR.md").stat().st_mtime_ns)
    assert before == after


def test_changed_tldr_rewrites_both_and_exits_one(tmp_path: Path) -> None:
    story = _write(
        tmp_path, _STORY.replace("**TL;DR:** Second.", "**TL;DR:** Second, revised."), _TLDR
    )
    assert _load().main(["x", str(story)]) == 1
    assert "| [02](#entry-02) | Phase 1: storage | Second, revised. |" in story.read_text()
    tldr = (tmp_path / "README_TLDR.md").read_text()
    assert "Preamble that must survive." in tldr
    assert "### [02 — Phase 1: storage](README.md#entry-02)\n\nSecond, revised.\n" in tldr
    # A second run finds nothing to do.
    assert _load().main(["x", str(story)]) == 0


def test_missing_tldr_is_refused_with_the_entry_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _STORY.replace("**TL;DR:** Second.\n\n", "")
    story = _write(tmp_path, broken, _TLDR)
    assert _load().main(["x", str(story)]) == 2
    assert "entries without a TL;DR paragraph: 02" in capsys.readouterr().err
    assert (tmp_path / "README_TLDR.md").read_text() == _TLDR  # nothing written


def test_gap_in_numbering_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    story = _write(tmp_path, _STORY.replace("### 02 —", "### 03 —"), _TLDR)
    assert _load().main(["x", str(story)]) == 2
    assert "not numbered 01..02 in order" in capsys.readouterr().err


def test_missing_file_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _load().main(["x", str(tmp_path / "README.md")]) == 2
    assert "is not a file" in capsys.readouterr().err


def test_the_real_build_story_parses() -> None:
    module = _load()
    entries = module.parse_entries((_REPO_ROOT / "docs/prompts/README.md").read_text())
    assert len(entries) >= 24
