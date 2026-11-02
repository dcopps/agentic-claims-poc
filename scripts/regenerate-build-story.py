#!/usr/bin/env python3
"""
Regenerate the build story's at-a-glance table and `README_TLDR.md` from its entries.

    uv run python scripts/regenerate-build-story.py [docs/prompts/README.md]

The build story (`docs/prompts/README.md`) holds one entry per phase, each
opening with a `### NN — Title` heading and a `**TL;DR:**` paragraph. Two
other copies of those paragraphs exist: the at-a-glance table at the top of the
same file, and `README_TLDR.md` beside it. The standing rule is that both are
regenerated from the entries at every close-out, never edited by hand. This
script is that rule as a command.

Strategy: read the entries, refuse anything malformed before writing, rewrite
both derived copies, and report through the exit code so a run that changed
something tells the author to commit:

    0  both files were already identical to the entries (nothing written)
    1  one or both files differed and have been rewritten
    2  the entries could not be parsed (nothing written; the reason is printed)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STORY = Path("docs/prompts/README.md")
TLDR_FILENAME = "README_TLDR.md"

_ENTRY_RE = re.compile(r"^### (\d\d) — (.+?)\n\n\*\*TL;DR:\*\* (.+?)\n", re.M)
_HEADING_RE = re.compile(r"^### (\d\d) — ", re.M)
_TABLE_RE = re.compile(r"(\| # \| Phase \| TL;DR \|\n\|---\|---\|---\|\n)(?:\|.*\n)+")
_TLDR_FIRST_ENTRY = "### ["

EXIT_UNCHANGED = 0
EXIT_REWRITTEN = 1
EXIT_REFUSED = 2


@dataclass(frozen=True)
class Entry:
    number: str
    title: str
    tldr: str


class StoryFormatError(ValueError):
    """The build story does not have the shape the regeneration relies on."""


def parse_entries(story_text: str) -> list[Entry]:
    """Every entry in order; refuse a gap in the numbering or a heading with no TL;DR."""
    headings = _HEADING_RE.findall(story_text)
    entries = [Entry(n, title, tldr) for n, title, tldr in _ENTRY_RE.findall(story_text)]
    if not entries:
        raise StoryFormatError("no `### NN — Title` entries with a **TL;DR:** paragraph found")
    with_tldr = {entry.number for entry in entries}
    missing = [n for n in headings if n not in with_tldr]
    if missing:
        raise StoryFormatError(f"entries without a TL;DR paragraph: {', '.join(missing)}")
    expected = [f"{i:02d}" for i in range(1, len(entries) + 1)]
    actual = [entry.number for entry in entries]
    if actual != expected:
        raise StoryFormatError(
            f"entries are not numbered 01..{len(entries):02d} in order: {actual}"
        )
    return entries


def render_table_rows(entries: list[Entry]) -> str:
    return "".join(f"| [{e.number}](#entry-{e.number}) | {e.title} | {e.tldr} |\n" for e in entries)


def render_tldr_entries(entries: list[Entry]) -> str:
    return "".join(
        f"### [{e.number} — {e.title}](README.md#entry-{e.number})\n\n{e.tldr}\n\n" for e in entries
    )


def regenerate_story(story_text: str, entries: list[Entry]) -> str:
    """The story with its at-a-glance rows replaced; refuse if the table is not where expected."""
    match = _TABLE_RE.search(story_text)
    if match is None:
        raise StoryFormatError("the at-a-glance table (`| # | Phase | TL;DR |`) was not found")
    return (
        story_text[: match.start()]
        + match.group(1)
        + render_table_rows(entries)
        + story_text[match.end() :]
    )


def regenerate_tldr(tldr_text: str, entries: list[Entry]) -> str:
    """The TL;DR file with everything from its first entry heading replaced."""
    cut = tldr_text.find(_TLDR_FIRST_ENTRY)
    if cut < 0:
        raise StoryFormatError(
            f"{TLDR_FILENAME} has no `{_TLDR_FIRST_ENTRY}` entry heading to replace from"
        )
    return tldr_text[:cut] + render_tldr_entries(entries)


def main(argv: list[str]) -> int:
    story_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_STORY
    tldr_path = story_path.with_name(TLDR_FILENAME)
    for path in (story_path, tldr_path):
        if not path.is_file():
            print(f"refused: {path} is not a file", file=sys.stderr)
            return EXIT_REFUSED
    story_text = story_path.read_text(encoding="utf-8")
    tldr_text = tldr_path.read_text(encoding="utf-8")
    try:
        entries = parse_entries(story_text)
        new_story = regenerate_story(story_text, entries)
        new_tldr = regenerate_tldr(tldr_text, entries)
    except StoryFormatError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    changed = []
    if new_story != story_text:
        story_path.write_text(new_story, encoding="utf-8")
        changed.append(story_path.name)
    if new_tldr != tldr_text:
        tldr_path.write_text(new_tldr, encoding="utf-8")
        changed.append(tldr_path.name)
    if changed:
        print(f"rewritten from {len(entries)} entries: {', '.join(changed)} — review and commit")
        return EXIT_REWRITTEN
    print(f"unchanged: both files already match the {len(entries)} entries")
    return EXIT_UNCHANGED


if __name__ == "__main__":
    sys.exit(main(sys.argv))
