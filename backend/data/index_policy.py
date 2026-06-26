"""
Policy indexing script.

Reads `backend/data/sample_policy.txt`, splits it into chunks at heading
boundaries, embeds each chunk via `bge-small-en-v1.5`, and writes the
result to `policy_chunks`. Same model used at retrieval time — the
embedding model is a one-way door, locked in `CLAUDE.md`.

Run from the repo root:

    uv run python -m backend.data.index_policy

Idempotent: deletes prior rows for the same `source_path` before
inserting, all in one transaction so a partial failure leaves the
previous index intact.

The chunker is a small standalone function so it can be unit-tested
without loading the embedding model (which is slow).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from backend.db.connection import open_connection
from backend.settings import Settings

if TYPE_CHECKING:
    import psycopg
    from sentence_transformers import SentenceTransformer
    from transformers.tokenization_utils_base import PreTrainedTokenizerBase

# Path of the policy excerpt, relative to the repository root. Stored as
# the `source_path` column so a future re-index from a different file
# (e.g. an updated wording) overwrites the right rows.
_DEFAULT_POLICY_PATH: Path = Path("backend/data/sample_policy.txt")

# Section headings start with `# `. Anything else is body text. The
# chunker uses this to split sections without crossing boundaries.
_SECTION_PREFIX: str = "# "

# Target chunk size in tokens. The lower bound keeps chunks substantial
# enough for the embedding model to produce a meaningful signal; the
# upper bound stays under the bge-small context limit (512 tokens) with
# a comfortable margin.
_TARGET_TOKENS_MIN: int = 200
_TARGET_TOKENS_MAX: int = 300


@dataclass(frozen=True)
class PolicyChunk:
    """A single chunk ready to be embedded and inserted."""

    source_path: str
    section: str
    chunk_index: int
    content: str
    token_count: int


# --------------------------------------------------------------------------- #
# Chunking — model-free, pure function
# --------------------------------------------------------------------------- #


def chunk_markdown_sections(
    text: str,
    source_path: str,
    token_counter: PreTrainedTokenizerBase,
    *,
    target_min: int = _TARGET_TOKENS_MIN,
    target_max: int = _TARGET_TOKENS_MAX,
) -> list[PolicyChunk]:
    """
    Split `text` into chunks at heading boundaries, packed near the
    target token range, never crossing a section.

    Defensive guards:
      - empty text aborts (no chunks to write is a bug, not a state).
      - text without any `# ` heading aborts (the file shape is part of
        the contract; a missing heading means the chunker would emit a
        single megachunk).
      - target_min must be <= target_max, both must be positive.
    """
    if not text.strip():
        raise ValueError("chunk_markdown_sections: refusing to chunk empty text")
    if target_min <= 0 or target_max <= 0:
        raise ValueError(
            "chunk_markdown_sections: target_min and target_max must be positive; "
            f"got target_min={target_min}, target_max={target_max}"
        )
    if target_min > target_max:
        raise ValueError(
            "chunk_markdown_sections: target_min must be <= target_max; "
            f"got target_min={target_min}, target_max={target_max}"
        )

    sections = _split_into_sections(text)
    if not sections:
        raise ValueError(
            "chunk_markdown_sections: no `# ` headings found — the policy "
            "file must be section-delimited"
        )

    chunks: list[PolicyChunk] = []
    chunk_index = 0
    for section_name, paragraphs in sections:
        for body in _pack_paragraphs(paragraphs, token_counter, target_max):
            token_count = _count_tokens(body, token_counter)
            chunks.append(
                PolicyChunk(
                    source_path=source_path,
                    section=section_name,
                    chunk_index=chunk_index,
                    content=body,
                    token_count=token_count,
                )
            )
            chunk_index += 1

    return chunks


def _split_into_sections(text: str) -> list[tuple[str, list[str]]]:
    """Group lines into (section_name, paragraph_list) tuples."""
    sections: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_paragraphs: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            current_paragraphs.append(" ".join(paragraph_lines).strip())
            paragraph_lines.clear()

    def flush_section() -> None:
        if current_name is not None:
            flush_paragraph()
            non_empty = [p for p in current_paragraphs if p]
            if non_empty:
                sections.append((current_name, non_empty))

    for line in text.splitlines():
        if line.startswith(_SECTION_PREFIX):
            flush_section()
            current_name = line[len(_SECTION_PREFIX):].strip()
            current_paragraphs = []
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph_lines.append(line.strip())

    flush_section()
    return sections


def _pack_paragraphs(
    paragraphs: list[str],
    token_counter: PreTrainedTokenizerBase,
    target_max: int,
) -> list[str]:
    """
    Pack paragraphs into chunks until adding the next would exceed
    target_max tokens. Each emitted chunk is non-empty.
    """
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = _count_tokens(paragraph, token_counter)
        if buffer and buffer_tokens + paragraph_tokens > target_max:
            chunks.append("\n\n".join(buffer))
            buffer = []
            buffer_tokens = 0
        buffer.append(paragraph)
        buffer_tokens += paragraph_tokens

    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def _count_tokens(text: str, token_counter: PreTrainedTokenizerBase) -> int:
    """Count tokens via the embedding model's tokenizer."""
    return len(token_counter.encode(text, add_special_tokens=False))


# --------------------------------------------------------------------------- #
# Embedding + persistence
# --------------------------------------------------------------------------- #


def _load_model(settings: Settings) -> tuple[SentenceTransformer, PreTrainedTokenizerBase]:
    """Load the embedding model and its tokenizer once; reused per run."""
    # Imported here so unit tests of the chunker don't pay the model load.
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer

    model = SentenceTransformer(settings.embedding.model_name)
    tokenizer = AutoTokenizer.from_pretrained(settings.embedding.model_name)
    return model, tokenizer


def _embed_chunks(
    chunks: list[PolicyChunk],
    model: SentenceTransformer,
    settings: Settings,
) -> list[np.ndarray]:
    """Embed `chunks` in batches; return one vector per chunk."""
    contents = [c.content for c in chunks]
    vectors = model.encode(
        contents,
        batch_size=settings.embedding.batch_size,
        normalize_embeddings=settings.embedding.normalise_embeddings,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    if vectors.shape[1] != settings.embedding.dimension:
        raise ValueError(
            "embedding model produced unexpected dimension; "
            f"expected {settings.embedding.dimension}, got {vectors.shape[1]}"
        )
    return [v for v in vectors]


_DELETE_SQL = "DELETE FROM policy_chunks WHERE source_path = %s"

_INSERT_SQL = """
INSERT INTO policy_chunks (
    source_path, section, chunk_index, content, token_count,
    embedding, embedding_model
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


def _persist(
    conn: psycopg.Connection,
    chunks: list[PolicyChunk],
    vectors: list[np.ndarray],
    embedding_model_name: str,
) -> None:
    """Replace existing chunks for the same source_path in one transaction."""
    if len(chunks) != len(vectors):
        raise ValueError(
            "_persist: chunk count mismatch — "
            f"{len(chunks)} chunks vs {len(vectors)} vectors"
        )

    source_path = chunks[0].source_path
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(_DELETE_SQL, (source_path,))
        for chunk, vector in zip(chunks, vectors, strict=True):
            cur.execute(
                _INSERT_SQL,
                (
                    chunk.source_path,
                    chunk.section,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.token_count,
                    vector.tolist(),
                    embedding_model_name,
                ),
            )


def main(argv: list[str] | None = None) -> int:
    settings = Settings()
    policy_path = _DEFAULT_POLICY_PATH
    if not policy_path.exists():
        raise FileNotFoundError(
            f"index_policy: source file missing at {policy_path.resolve()}"
        )

    text = policy_path.read_text(encoding="utf-8")
    model, tokenizer = _load_model(settings)
    chunks = chunk_markdown_sections(text, str(policy_path), tokenizer)
    vectors = _embed_chunks(chunks, model, settings)

    with open_connection(settings) as conn:
        # `_persist` wraps its delete+insert in `conn.transaction()`, which
        # commits on exit — under the connection's autocommit contract no outer
        # commit is needed here.
        _persist(conn, chunks, vectors, settings.embedding.model_name)

    total_tokens = sum(c.token_count for c in chunks)
    print(
        f"Indexed {len(chunks)} chunks "
        f"({total_tokens} total tokens) "
        f"using {settings.embedding.model_name} "
        f"into policy_chunks where source_path={policy_path}."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
