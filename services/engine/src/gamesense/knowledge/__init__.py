"""Curated game knowledge packs and FTS5 retrieval for prompt assembly."""

from .index import Hit, KnowledgeBase, query_terms
from .pack import Chunk, Doc, PackError, default_knowledge_dir, load_docs, parse_doc

__all__ = [
    "Chunk",
    "Doc",
    "Hit",
    "KnowledgeBase",
    "PackError",
    "default_knowledge_dir",
    "load_docs",
    "parse_doc",
    "query_terms",
]
