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

## Live coaching (Milestone 1)

The coach is configured through environment variables or a `.env` file at the repo root. Start from the template:

```bash
cp .env.example .env
```

By default `GAMESENSE_PROVIDER=mock`, a free offline coach that never reads pixels. Use it to exercise the full pipeline (triggers, cooldowns, overlay, hotkeys) at no cost. To use a real model, set the provider and its key:

```bash
GAMESENSE_PROVIDER=anthropic   # Claude Haiku 5.5
ANTHROPIC_API_KEY=sk-ant-...
# or
GAMESENSE_PROVIDER=google      # Gemini 3.1 Flash-Lite
GEMINI_API_KEY=...
```

`GAMESENSE_HOURLY_BUDGET_USD` (default `0.50`) is a hard cap on estimated spend per rolling hour. The dashboard shows calls, tips, spend and latency.

**Overlay hotkeys** (global):

| Action | Shortcut |
| --- | --- |
| Dismiss tip | `Alt+Shift+X` |
| Mark tip useful | `Alt+Shift+Up` |
| Mark tip not useful | `Alt+Shift+Down` |
| Pause or resume coaching | `Alt+Shift+P` |

### What works where

| | macOS (replay) | Windows desktop (live game) |
| --- | --- | --- |
| Engine, coach, model calls, spend cap | Yes | Yes |
| Dashboard and overlay window | Yes | Yes |
| Live game capture (Windows Graphics Capture) | No | Yes |
| Game auto-detection from the foreground window | No (set `GAMESENSE_GAME`) | Yes |
| FPS and RAM impact on a real game | No | Yes |

**Testing on the Windows desktop:**

1. Set the game to **borderless windowed** (overlays can't draw over exclusive fullscreen).
2. In `.env`, set `GAMESENSE_CAPTURE=window`, then set `GAMESENSE_WINDOW` to part of the game's window title (or leave it empty to capture whatever window is in front when the engine starts).
3. Run `npm run dev`, switch to the game, and play. Tips appear top-right.
4. Check the dashboard's **App memory** figure while playing. Its budget is 300 MB (ADR-002); if it stays well above that, we switch the shell to Tauri.

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
- **API keys:** never put provider keys in the renderer or commit them. They live in the local `.env` file (gitignored), which only the engine reads, until the OS keychain integration lands.
- **Gameplay footage:** don't commit it. Clips stay in `evals/clips/`, which is gitignored.
- **Branches and PRs:** one milestone issue (or part of one) per PR, and CI must be green before merging.
