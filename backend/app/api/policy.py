"""
Policy API — the indexed policy, as retrieval sees it (Prompt 27).

`GET /api/policy` returns every row of `policy_chunks` under the configured
policy source, in document order and grouped by section, so the Policy page
shows exactly the passages the Validator's similarity search runs over — the
table, not the text file. The source is resolved with the same expression the
Validator uses (`str(settings.retrieval.policy_source_path)`), so the page and
retrieval cannot disagree.

What is deliberately not returned: the embedding vectors. The query names its
columns and the response models forbid extras, and a test asserts the word
`embedding` never appears in the body. An un-indexed deployment is a state,
not an error: it answers with a count of zero and an empty section list.

Unauthenticated like the rest of `/api`: the policy text is synthetic and
already public in the repository, and nothing here carries a secret.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.db.connection import open_connection
from backend.settings import Settings

policy_router = APIRouter(prefix="/policy", tags=["policy"])

# The columns the table is read with. `embedding` is absent by design; the
# "no vectors" test guards the omission.
_SELECT_PASSAGES = """
SELECT chunk_id, section, chunk_index, content, token_count, embedding_model
FROM policy_chunks
WHERE source_path = %s
ORDER BY chunk_index
"""


class PolicyPassageView(BaseModel):
    """One indexed passage. `position` is 1-based within its section."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    section: str
    chunk_index: int
    position: int
    section_size: int
    text: str
    token_count: int


class PolicySectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passages: list[PolicyPassageView]


class PolicyIndexView(BaseModel):
    """The whole indexed policy; `embedding_model` is None when nothing is indexed."""

    model_config = ConfigDict(extra="forbid")

    source: str
    embedding_model: str | None
    passage_count: int
    sections: list[PolicySectionView]


# One row of `_SELECT_PASSAGES`, in column order.
PassageRow = tuple[UUID, str, int, str, int, str]


@policy_router.get("", response_model=PolicyIndexView)
async def get_policy(settings: Settings = Depends(get_settings)) -> PolicyIndexView:
    """The indexed policy for the configured source, grouped by section in document order."""
    return await run_in_threadpool(_read_policy, settings)


def _read_policy(settings: Settings) -> PolicyIndexView:
    source = str(settings.retrieval.policy_source_path)
    with open_connection(settings) as conn:
        rows = _fetch_rows(conn, source)
    return group_passages(source, rows)


def _fetch_rows(conn: psycopg.Connection, source: str) -> list[PassageRow]:
    with conn.cursor() as cur:
        cur.execute(_SELECT_PASSAGES, (source,))
        return [_as_row(row) for row in cur.fetchall()]


def _as_row(raw: tuple[object, ...]) -> PassageRow:
    # The cursor yields untyped tuples; naming the six columns here is what lets
    # the grouping below stay typed without a cast at every use.
    chunk_id, section, chunk_index, content, token_count, model = raw
    assert isinstance(chunk_id, UUID) and isinstance(section, str)
    assert isinstance(chunk_index, int) and isinstance(content, str)
    assert isinstance(token_count, int) and isinstance(model, str)
    return (chunk_id, section, chunk_index, content, token_count, model)


def group_passages(source: str, rows: list[PassageRow]) -> PolicyIndexView:
    """
    Group ordered rows into sections, numbering each passage within its section.

    Pure: no database access, so the grouping and its one guard can be tested
    directly. Sections keep the order in which they first appear by
    `chunk_index`, which is the document's order. Rows naming more than one
    embedding model abort: a mixed index would make every similarity in it
    meaningless, and that must be visible rather than averaged away.
    """
    models = sorted({row[5] for row in rows})
    if len(models) > 1:
        raise ValueError(
            "policy_chunks: expected one embedding_model for the source; "
            f"found {models} under source_path={source!r}"
        )
    by_section: dict[str, list[PassageRow]] = {}
    for row in rows:
        by_section.setdefault(row[1], []).append(row)
    sections = [_section_view(name, members) for name, members in by_section.items()]
    return PolicyIndexView(
        source=source,
        embedding_model=models[0] if models else None,
        passage_count=len(rows),
        sections=sections,
    )


def _section_view(name: str, members: list[PassageRow]) -> PolicySectionView:
    size = len(members)
    passages = [
        PolicyPassageView(
            chunk_id=chunk_id,
            section=section,
            chunk_index=chunk_index,
            position=position,
            section_size=size,
            text=content,
            token_count=token_count,
        )
        for position, (chunk_id, section, chunk_index, content, token_count, _model) in enumerate(
            members, start=1
        )
    ]
    return PolicySectionView(name=name, passages=passages)
