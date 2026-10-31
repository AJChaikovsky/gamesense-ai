"""Loads curated knowledge packs: markdown files with a small front-matter header.

    knowledge/<game_id>/<topic>.md

    ---
    title: CS2 economy
    game: cs2
    source: GameSense curated (general knowledge); Valve CS2 update notes
    version: CS2, October 2026
    updated: 2026-10-31
    tags: money, buy, loss bonus
    core: false
    ---
    ## Loss bonus
    ...

Each ``##`` section becomes one retrievable chunk. Docs marked ``core: true`` are
short must-know summaries that go into the (cacheable) system prompt instead.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = ("title", "game", "source", "version", "updated")


class PackError(ValueError):
    """A knowledge doc is malformed (missing front matter or required fields)."""


@dataclass(frozen=True, slots=True)
class Chunk:
    doc_id: str  # "<game>/<file stem>"
    game: str
    title: str
    heading: str
    body: str
    tags: str
    source: str
    version: str


@dataclass(frozen=True, slots=True)
class Doc:
    doc_id: str
    path: Path
    meta: dict[str, str]
    body: str

    @property
    def game(self) -> str:
        return self.meta["game"]

    @property
    def core(self) -> bool:
        return self.meta.get("core", "false").lower() == "true"

    def chunks(self) -> list[Chunk]:
        out = []
        for heading, body in split_sections(self.body):
            out.append(
                Chunk(
                    doc_id=self.doc_id,
                    game=self.game,
                    title=self.meta["title"],
                    heading=heading,
                    body=body,
                    tags=self.meta.get("tags", ""),
                    source=self.meta["source"],
                    version=self.meta["version"],
                )
            )
        return out


def parse_doc(path: Path, root: Path) -> Doc:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        raise PackError(f"{path}: missing front matter (--- ... ---)")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, sep, value = line.partition(":")
            if not sep:
                raise PackError(f"{path}: bad front matter line {line!r}")
            meta[key.strip().lower()] = value.strip()
    missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
    if missing:
        raise PackError(f"{path}: missing front matter fields {missing}")
    rel = path.relative_to(root)
    return Doc(f"{rel.parent.as_posix()}/{path.stem}", path, meta, match.group(2).strip())


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split on ``## `` headings; text before the first heading is an intro section."""
    sections: list[tuple[str, str]] = []
    heading, lines = "Overview", list[str]()
    for line in body.splitlines():
        if line.startswith("## "):
            if "\n".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if "\n".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def load_docs(root: Path) -> list[Doc]:
    if not root.is_dir():
        return []
    return [
        parse_doc(path, root)
        for path in sorted(root.glob("*/*.md"))
        if path.name.lower() != "readme.md"
    ]


def default_knowledge_dir() -> Path | None:
    """``$GAMESENSE_KNOWLEDGE_DIR``, else the repo's ``knowledge/`` folder (dev checkout)."""
    raw = os.environ.get("GAMESENSE_KNOWLEDGE_DIR")
    if raw:
        return Path(raw).expanduser()
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for folder in (start, *start.parents):
            candidate = folder / "knowledge"
            if (candidate / "README.md").is_file() and (folder / "pyproject.toml").is_file():
                return candidate
    return None
