"""Check and search the knowledge packs.

uv run gamesense-knowledge check
uv run gamesense-knowledge search cs2 "bomb planted no kit"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..games.registry import KNOWN_GAMES
from .index import KnowledgeBase, query_terms
from .pack import PackError, default_knowledge_dir, load_docs

MAX_CORE_CHARS = 1500
MAX_CHUNK_CHARS = 700


def check(root: Path) -> list[str]:
    """Problems with the packs under ``root`` (empty when everything is fine)."""
    try:
        docs = load_docs(root)
    except PackError as exc:
        return [str(exc)]
    known = {g.game_id for g in KNOWN_GAMES}
    problems: list[str] = []
    cores: dict[str, int] = {}
    for doc in docs:
        folder = doc.doc_id.split("/", 1)[0]
        if doc.game != folder:
            problems.append(f"{doc.path}: game {doc.game!r} does not match folder {folder!r}")
        if doc.game not in known:
            problems.append(f"{doc.path}: unknown game id {doc.game!r}")
        if doc.core:
            cores[doc.game] = cores.get(doc.game, 0) + 1
            if len(doc.body) > MAX_CORE_CHARS:
                problems.append(f"{doc.path}: core is {len(doc.body)} chars (max {MAX_CORE_CHARS})")
            continue
        for chunk in doc.chunks():
            if len(chunk.body) > MAX_CHUNK_CHARS:
                problems.append(
                    f"{doc.path}: section {chunk.heading!r} is {len(chunk.body)} chars"
                    f" (max {MAX_CHUNK_CHARS})"
                )
    problems += [f"{game}: {n} core docs (max 1)" for game, n in cores.items() if n > 1]
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gamesense-knowledge", description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)  # fmt: skip
    parser.add_argument("--dir", type=Path, default=None, help="knowledge folder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate front matter and sizes")
    p_search = sub.add_parser("search", help="show what the coach would retrieve")
    p_search.add_argument("game")
    p_search.add_argument("text")
    p_search.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    root = args.dir or default_knowledge_dir()
    if root is None:
        raise SystemExit("knowledge folder not found; pass --dir")
    if args.command == "check":
        problems = check(root)
        for p in problems:
            print(p)
        docs = load_docs(root) if not problems else []
        print(f"{len(docs)} docs OK" if not problems else f"{len(problems)} problem(s)")
        raise SystemExit(1 if problems else 0)
    kb = KnowledgeBase.load(root)
    terms = query_terms([args.text])
    print(f"terms: {terms}")
    for hit in kb.search(args.game, terms, limit=args.limit):
        print(f"\n{hit.score:.2f}  {hit.chunk.doc_id} > {hit.chunk.heading}\n{hit.chunk.body}")


if __name__ == "__main__":
    main()
