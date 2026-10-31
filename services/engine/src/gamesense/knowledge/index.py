"""SQLite FTS5 index over knowledge-pack chunks, and situational retrieval.

The packs are small (tens of KB), so the index is built in memory at startup in
a few milliseconds and a query takes well under one. Nothing here calls a model.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .pack import Chunk, Doc, default_knowledge_dir, load_docs

log = logging.getLogger(__name__)

_STOPWORD_TEXT = (
    "the and for are but not you your with this that from have has was were will can "
    "into onto off out over under then than when what where which who why how all "
    "any each few more most other some such only own same too very just now unknown "
    "none true false yes player game screen visible round phase map team holding "
    "score competitive"
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())
# bm25 weights by column: doc_id, game (unindexed), title, heading, body, tags.
_WEIGHTS = "0.0, 0.0, 1.0, 4.0, 1.0, 0.5"


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float  # bm25: lower is better


def query_terms(texts: Iterable[str], limit: int = 24) -> list[str]:
    """Plain search words from free text (observation names, activities, telemetry)."""
    seen: dict[str, None] = {}
    for text in texts:
        for word in re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")):
            if len(word) >= 3 and word not in _STOPWORDS and not word.isdigit():
                seen.setdefault(word, None)
    return list(seen)[:limit]


class KnowledgeBase:
    def __init__(self, docs: Sequence[Doc]) -> None:
        self.docs = list(docs)
        self._core = {d.game: d.body for d in self.docs if d.core}
        self._chunks: list[Chunk] = [c for d in self.docs if not d.core for c in d.chunks()]
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self.fts = True
        try:
            self._db.execute(
                "CREATE VIRTUAL TABLE chunks USING fts5("
                "doc_id UNINDEXED, game UNINDEXED, title, heading, body, tags,"
                " tokenize='porter unicode61')"
            )
        except sqlite3.OperationalError:  # SQLite built without FTS5
            log.warning("SQLite has no FTS5; knowledge retrieval is off")
            self.fts = False
            return
        self._db.executemany(
            "INSERT INTO chunks(rowid, doc_id, game, title, heading, body, tags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (i, c.doc_id, c.game, c.title, c.heading, c.body, c.tags)
                for i, c in enumerate(self._chunks)
            ],
        )

    @classmethod
    def load(cls, root: Path | None = None) -> KnowledgeBase:
        root = root or default_knowledge_dir()
        docs = load_docs(root) if root else []
        kb = cls(docs)
        log.info("knowledge: %d docs, %d chunks from %s", len(docs), len(kb._chunks), root)
        return kb

    @property
    def games(self) -> set[str]:
        return {d.game for d in self.docs}

    def core(self, game_id: str) -> str:
        """The game's must-know summary for the system prompt ('' if none)."""
        return self._core.get(game_id, "")

    def search(self, game_id: str, terms: Sequence[str], limit: int = 3) -> list[Hit]:
        if not self.fts or not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        rows = self._db.execute(
            f"SELECT rowid, bm25(chunks, {_WEIGHTS}) AS score FROM chunks"
            " WHERE chunks MATCH ? AND game = ? ORDER BY score LIMIT ?",
            (match, game_id, limit),
        ).fetchall()
        return [Hit(self._chunks[rowid], score) for rowid, score in rows]

    def for_situation(
        self, game_id: str, situation: Iterable[str], *, limit: int = 3, max_chars: int = 900
    ) -> list[str]:
        """Snippets relevant to the current situation, ready for the prompt."""
        out: list[str] = []
        used = 0
        for hit in self.search(game_id, query_terms(situation), limit=limit):
            body = " ".join(hit.chunk.body.split())
            snippet = f"[{hit.chunk.heading}] {body}"
            if used + len(snippet) > max_chars:
                room = max_chars - used
                if room < 120:
                    break
                snippet = snippet[: room - 1].rsplit(" ", 1)[0] + "…"
            out.append(snippet)
            used += len(snippet)
        return out
