# GameSense AI

A universal, proactive AI gaming coach. GameSense watches your game, works out what is happening, gives short live tips in an overlay, and learns your habits over time so its coaching improves along with you.

It observes and recommends. It never sends inputs, reads game memory or touches anti-cheat.

> **Status:** Milestone 1 (first live tip). The engine captures gameplay (live on Windows, recorded clips anywhere), asks a vision model for advice and shows validated tips in a click-through overlay. See [CONTRIBUTING.md](CONTRIBUTING.md) to set up and run it, and [`docs/`](docs/) for the plan.

## Documents

| Doc | What it covers |
| --- | --- |
| [Architecture](docs/architecture.md) | Subsystems, data contracts, real-time pipeline, memory, game adapters |
| [Tech stack decisions](docs/decisions.md) | Language, desktop shell, UI, database, AI providers, and why each was chosen |
| [Model selection](docs/model-selection.md) | Current model pricing, cost-per-hour estimates and the benchmark plan |
| [UI design](docs/ui-design.md) | Overlay and dashboard design principles |
| [Milestones](docs/milestones.md) | The build plan, from first live tip to a paid subscription |

## Stack at a glance

- **Desktop:** Electron with React, TypeScript, Tailwind and shadcn/ui for the overlay and dashboard (Tauri is the fallback if RAM use is too high)
- **Engine:** Python 3.12 local service (asyncio, FastAPI and WebSocket), screen capture via Windows Graphics Capture, OpenCV, ONNX Runtime
- **Storage:** SQLite (WAL, FTS5, sqlite-vec) behind a repository interface; PostgreSQL later for cloud accounts
- **AI:** provider-agnostic interface over Claude, Gemini, OpenAI and Meta Muse. Models are chosen by benchmark, starting with a cheap, fast vision model for live tips and a stronger model for session reviews
- **Platform:** Windows first (developed on macOS using recorded-gameplay replay)

## First supported games

| Game | Genre | Integration |
| --- | --- | --- |
| Counter-Strike 2 | FPS | Screen + official Game State Integration (Tier 3) |
| A FromSoftware-style action RPG | RPG | Screen only (Tier 1 to 2) |
| Minecraft | Sandbox | Screen first, optional mod telemetry later (Tier 1 to 3) |

## Repository layout

```
apps/desktop/         Electron + React overlay, onboarding, settings, session dashboard
services/engine/      Python engine: capture, perception, coaching, knowledge, memory, API
packages/contracts/   Shared data contracts (Pydantic models, exported JSON Schema, generated TS types)
knowledge/            Curated per-game knowledge documents
evals/                Eval dataset manifests, harness and reports
docs/                 Architecture and planning docs
```
