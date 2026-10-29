# Developing GameSense

GameSense is a monorepo with a Python engine and an Electron desktop app. You can develop most of it on macOS using recorded gameplay. Live capture and the in-game overlay need the Windows PC.

## Prerequisites (macOS and Windows)

| Tool | Version | Install |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | macOS: `brew install uv` · Windows: `winget install astral-sh.uv` |
| Node.js | 22 LTS | macOS: `brew install node@22` · Windows: `winget install OpenJS.NodeJS.LTS` |
| Git | any recent | |

uv installs the right Python (3.12) on its own.

## First-time setup

```bash
git clone https://github.com/AJChaikovsky/gamesense-ai.git
cd gamesense-ai
uv sync          # Python engine + contracts + dev tools into .venv
npm install      # desktop app + contracts type generator
npm run sample-clip   # writes evals/clips/sample.mp4 (synthetic test footage)
```

## Run it

```bash
npm run dev
```

This starts the Electron app with hot reload. The app launches the Python engine itself (`uv run gamesense-engine`) and passes it a per-launch token. The dashboard should show "Engine connected" with live capture stats from the replay clip.

To replay your own recording instead of the sample, set `GAMESENSE_REPLAY`:

```bash
GAMESENSE_REPLAY=~/Movies/cs2-round.mp4 npm run dev          # macOS
$env:GAMESENSE_REPLAY="C:\clips\cs2-round.mp4"; npm run dev  # Windows PowerShell
```

You can also run the engine on its own, which is useful for debugging:

```bash
uv run gamesense-engine --replay evals/clips/sample.mp4 --token dev
# prints {"event": "ready", "port": 54321}; then:
curl -H "x-gamesense-token: dev" http://127.0.0.1:54321/health
```

## Checks (same as CI)

```bash
npm run check:engine   # ruff lint + format check, mypy (strict), pytest
npm run check          # desktop typecheck + vitest
```

## Changing a data contract

The Pydantic models in `packages/contracts/src/gamesense_contracts/` are the source of truth. After editing them:

```bash
npm run contracts:gen
```

This regenerates `packages/contracts/schema/contracts.schema.json` and `packages/contracts/ts/index.ts`. Commit both. CI fails if they are stale.

## Layout

```
apps/desktop/          Electron main process (src/main), preload bridge (src/preload), React UI (src/renderer)
services/engine/       Python engine package `gamesense`
packages/contracts/    Shared contracts: Pydantic models, JSON Schema, generated TS types
evals/                 Eval datasets (clips are gitignored; keep them in evals/clips/)
knowledge/             Curated game knowledge packs
docs/                  Architecture, decisions, milestones
```

## Rules of the road

- **Shell independence:** React code never imports Electron. Everything the renderer needs from the shell goes through `window.gamesense` (`apps/desktop/src/shared/bridge.ts`), so a move to Tauri only touches the preload.
- **Engine and UI coupling:** the engine talks to the UI over its local WebSocket only.
- **API keys:** never put provider keys in the renderer or commit them. Use a local `.env` file (gitignored) until the OS keychain integration lands.
- **Gameplay footage:** don't commit it. Clips stay in `evals/clips/`, which is gitignored.
- **Branches and PRs:** one milestone issue (or part of one) per PR, and CI must be green before merging.
