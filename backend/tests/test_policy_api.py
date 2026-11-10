"""
Tests for `GET /api/policy` — the indexed policy as retrieval sees it (Prompt 27).

Rows are inserted into `policy_chunks` by SQL with a deterministic vector, under
the source the test settings scope retrieval to, then the API is hit over a
TestClient. The grouping function is also tested directly, because its one guard
(mixed embedding models) surfaces as a server exception that TestClient re-raises.

Mutation proof (recorded in the Prompt 27 report, applied / observed / reverted):
adding `embedding` to the router's SELECT and to the passage view fails
`test_response_carries_no_vectors` on both of its assertions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.api.policy import PassageRow, group_passages
from backend.app.main import create_app
from backend.settings import Settings

_MODEL = "BAAI/bge-small-en-v1.5"
_PASSAGE_KEYS = {
    "chunk_id",
    "section",
    "chunk_index",
    "position",
    "section_size",
    "text",
    "token_count",
}


def _vector(seed: int) -> list[float]:
    """A unit-length 384-float vector, distinct per seed, stable across runs."""
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(384).astype(np.float32)
    values: list[float] = (raw / np.linalg.norm(raw)).tolist()
    return values


def _insert_chunk(
    conn: psycopg.Connection,
    *,
    source: str,
    section: str,
    chunk_index: int,
    content: str,
    model: str = _MODEL,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO policy_chunks (
                source_path, section, chunk_index, content, token_count,
                embedding, embedding_model
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING chunk_id
            """,
            (
                source,
                section,
                chunk_index,
                content,
                max(1, len(content) // 4),
                _vector(chunk_index),
                model,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    conn.commit()
    chunk_id: UUID = row[0]
    return chunk_id


def _source(settings: Settings) -> str:
    return str(settings.retrieval.policy_source_path)


def _get(settings: Settings) -> dict[str, Any]:
    with TestClient(create_app(settings)) as client:
        resp = client.get("/api/policy")
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def test_passages_grouped_by_section_in_document_order(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    source = _source(db_settings)
    # Inserted out of index order, across three sections; A has two passages.
    ids = {
        "C3": _insert_chunk(clean_db, source=source, section="C", chunk_index=3, content="c three"),
        "A0": _insert_chunk(clean_db, source=source, section="A", chunk_index=0, content="a zero"),
        "B1": _insert_chunk(clean_db, source=source, section="B", chunk_index=1, content="b one"),
        "A2": _insert_chunk(clean_db, source=source, section="A", chunk_index=2, content="a two"),
    }
    body = _get(db_settings)

    assert body["source"] == source
    assert body["embedding_model"] == _MODEL
    assert body["passage_count"] == 4
    assert [s["name"] for s in body["sections"]] == ["A", "B", "C"]

    section_a = body["sections"][0]["passages"]
    assert [p["chunk_id"] for p in section_a] == [str(ids["A0"]), str(ids["A2"])]
    assert [p["position"] for p in section_a] == [1, 2]
    assert {p["section_size"] for p in section_a} == {2}
    assert [p["chunk_index"] for p in section_a] == [0, 2]
    assert section_a[1]["text"] == "a two"
    assert section_a[1]["token_count"] == max(1, len("a two") // 4)
    assert body["sections"][2]["passages"][0]["section_size"] == 1


def test_empty_index_is_a_state_not_an_error(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    body = _get(db_settings)
    assert body == {
        "source": _source(db_settings),
        "embedding_model": None,
        "passage_count": 0,
        "sections": [],
    }


def test_scoped_to_the_configured_source(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    _insert_chunk(clean_db, source=_source(db_settings), section="A", chunk_index=0, content="ours")
    _insert_chunk(
        clean_db, source="elsewhere/policy.txt", section="Z", chunk_index=0, content="theirs"
    )
    body = _get(db_settings)
    assert body["passage_count"] == 1
    assert [s["name"] for s in body["sections"]] == ["A"]


def test_response_carries_no_vectors(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    source = _source(db_settings)
    _insert_chunk(clean_db, source=source, section="A", chunk_index=0, content="a zero")
    _insert_chunk(clean_db, source=source, section="A", chunk_index=1, content="a one")
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/policy")
    assert resp.status_code == 200
    # The body never mentions the column, and every passage has exactly the
    # documented keys — a `SELECT *` or an extra field fails here, not in a browser.
    assert "embedding" not in resp.text.replace("embedding_model", "")
    for section in resp.json()["sections"]:
        for passage in section["passages"]:
            assert set(passage) == _PASSAGE_KEYS


def test_mixed_embedding_models_abort() -> None:
    rows: list[PassageRow] = [
        (uuid4(), "A", 0, "a", 5, "model-one"),
        (uuid4(), "A", 1, "b", 5, "model-two"),
    ]
    expected = r"expected one embedding_model .* \['model-one', 'model-two'\]"
    with pytest.raises(ValueError, match=expected):
        group_passages("backend/data/sample_policy.txt", rows)


def test_group_passages_is_pure_on_empty_input() -> None:
    view = group_passages("x/policy.txt", [])
    assert view.model_dump(mode="json") == {
        "source": "x/policy.txt",
        "embedding_model": None,
        "passage_count": 0,
        "sections": [],
    }
