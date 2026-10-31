# Knowledge packs

Curated game knowledge used by the live coach. One folder per game id (`cs2`, `fromsoft_rpg`, `minecraft`). Each markdown file starts with front matter:

```markdown
---
title: CS2 economy and buying
game: cs2                     # must match the folder and a game id in games/registry.py
source: where the facts come from
version: game version or patch the facts were checked against
updated: 2026-10-31
tags: words players and models use for this topic (helps retrieval)
core: false                   # true = short must-know summary, sent in every system prompt
---
## Section heading
One focused section per topic. Each section is one retrievable chunk.
```

How the coach uses them:

- **`core.md`** (one per game) goes in the system prompt for that game. It is identical on every call, so providers can cache it. Keep it under 1,500 characters.
- **Every other section** is indexed in SQLite FTS5 when the engine starts. Before each model call, the coach searches it with the current situation (the model's last activity and observations, plus live game data such as "round phase freezetime" or "bomb planted"). It then adds the top 3 matches, up to about 900 characters, to the prompt.

Writing guidelines: be concrete and actionable, keep each section under 700 characters, and don't include anything that would only be true in one patch unless `version` says which. Run the checks after editing:

```bash
uv run gamesense-knowledge check
uv run gamesense-knowledge search cs2 "bomb planted no kit"
```
