# Tech stack decisions

These records build on AJ's GameSense AI Product Architecture v0.1. Each one gives the choice, the reasoning, and what would make us revisit it.

## Settled product decisions (v0.1, section 10)

| # | Decision | Choice |
| --- | --- | --- |
| 1 | Initial OS | Windows first |
| 2 | AI deployment | Hybrid: local monitoring, cloud reasoning |
| 3 | Game knowledge | General AI knowledge plus curated game knowledge |
| 4 | Coaching experience | Adaptive: immediate tips plus long-term coaching |
| 5 | First validation | One engine across 3 genres (CS2, FromSoft-style RPG, Minecraft) |

Additional constraints from AJ:

- Live tips must work in every phase. There is no post-session-only phase.
- Solo developer, comfortable in any language. Real-time efficiency comes first.
- The goal is a polished product, eventually sold as a monthly subscription that covers token usage. The Meta AI hackathon (Nov 4, 2026) is a soft target, not the goal.
- Keep API spend minimal until the core works and can be tested properly.
- Development happens on a MacBook Air M2. The target machine is a Windows desktop with an RTX 2080 Super (8 GB VRAM).

---

## ADR-001: Engine language is Python 3.12

**Choice:** a local Python service (asyncio, FastAPI with WebSocket, Pydantic v2, uv for dependencies) runs capture, perception, orchestration, knowledge and memory.

**Why:**

- The latency budget is dominated by the cloud model call (roughly 0.5 to 3 seconds), not by our code. The local work (grab frame, downscale, diff, encode a JPEG) takes milliseconds in Python because OpenCV, NumPy and the capture libraries run native code underneath.
- Every provider SDK (Anthropic, Google, OpenAI, Meta), ONNX Runtime, OCR libraries and eval tooling are first-class in Python. For a solo developer this saves the most time.
- Windows capture is available through native-backed packages (`windows-capture`, which wraps Windows Graphics Capture, and `dxcam`, which uses DXGI Desktop Duplication). Both reach 60+ FPS, far more than we sample.

**Rules that keep it fast:**

- The capture loop runs in its own thread and writes into a fixed-size ring buffer. The model call never blocks it.
- Frames stay as NumPy arrays. We downscale before any encode, and only encode the frames we actually send.
- If profiling ever shows a hot path in Python, move just that function to Rust (PyO3) or into the Tauri side. Don't rewrite the engine.

**Revisit if:** profiling on the 2080 Super shows the engine costing a noticeable number of game FPS, or the fast path can't hold its sampling rate.

## ADR-002: Desktop shell is Tauri 2, not Electron

**Choice:** Tauri 2 with a React, TypeScript and Vite frontend. The Python engine ships as a Tauri sidecar binary.

**Why:**

- It runs alongside a game, so idle footprint matters. Tauri uses the system WebView2 on Windows, so it uses far less RAM and disk than Electron, which bundles Chromium.
- It supports what the overlay needs: transparent, undecorated, always-on-top windows, click-through (`set_ignore_cursor_events`), global hotkeys, a system tray and a sidecar process.
- The UI code is the same React/TypeScript that AJ's v0.1 planned for Electron. Only the shell changes.

**Known limitation (applies to Electron too):** desktop overlays don't draw over exclusive-fullscreen games. Players need borderless or windowed mode, which all three launch games support. Onboarding has to check this and explain it.

**Revisit if:** WebView2 transparency or click-through misbehaves on the target machine. Electron is the drop-in fallback because the React code carries over.

## ADR-003: UI is React, Tailwind and shadcn/ui, with an overlay-first design

**Choice:** React 19, TypeScript, Tailwind CSS, shadcn/ui (Radix primitives) and Zustand for state. There are two window types: the **overlay** (click-through, glanceable tips) and the **dashboard** (settings, session reviews, skill profile). See [ui-design.md](ui-design.md).

**Why:** this is a fast, well-documented stack with accessible primitives, and it keeps the overlay bundle tiny.

## ADR-004: Storage is SQLite now, PostgreSQL in the cloud later

**Choice:** SQLite in WAL mode via SQLAlchemy 2 and Alembic migrations, behind repository interfaces. FTS5 provides keyword retrieval over knowledge documents. `sqlite-vec` adds embeddings later if keyword search falls short. The short-term memory (last 30 to 60 seconds) stays in process memory.

**Why:** it needs zero setup, it's a single file the user can inspect, export or delete (which supports our privacy promise), and it is fast enough for our write rate (a few rows per second at most). The repository interface lets the cloud tier add PostgreSQL (accounts, sync, billing) without touching the coaching code.

## ADR-005: AI goes through a provider-agnostic interface, and models are picked by benchmark

**Choice:** one `VisionModelProvider` interface with adapters for Anthropic, Google, OpenAI and Meta Muse. Model choice is configuration, per role:

- **Live role** (perception plus a quick coaching decision on each trigger): the cheapest, fastest vision model that passes our eval.
- **Deep role** (session review, habit analysis, hard situations): a stronger model, called rarely.

We start with one model call per trigger that returns both a `GameState` and an optional `CoachingDecision` as structured output. That avoids two round trips on the live path. We split perception and coaching into separate calls only if the eval shows a quality gain worth the extra latency.

**Why:** prices and quality change monthly, as the October 2026 price cuts show. The benchmark in Milestone 2 decides, not spec sheets. See [model-selection.md](model-selection.md) for current prices and estimates.

## ADR-006: The fast path runs locally on the CPU and GPU, without a local VLM at first

**Choice:** the fast path uses OpenCV (frame differencing, HUD region crops), lightweight OCR for HUD numbers, and official telemetry where it exists (CS2 Game State Integration). Small ONNX detectors (DirectML or CUDA) are optional per game later. A local vision-language model is out of scope for now.

**Why:** an 8 GB 2080 Super is already busy rendering the game. A local VLM would cost frames and still be slower and weaker than a cheap cloud model. A local model stays possible behind the same provider interface (for example, an offline mode later).

## ADR-007: Contracts are Pydantic models, exported to JSON Schema and TypeScript

**Choice:** `packages/contracts` defines `GameState`, `CoachingDecision`, `HabitObservation` and the event messages as Pydantic models. A build step exports JSON Schema and generates TypeScript types for the frontend. The same schemas are passed to models as structured-output schemas.

**Why:** there is one source of truth, the frontend stays type-safe, and model outputs are validated before anything acts on them.

## ADR-008: Cross-platform development through a replay capture source

**Choice:** capture is an interface with two implementations. `WindowsCaptureSource` reads a live game window. `ReplaySource` reads a recorded gameplay video at real-time speed.

**Why:** AJ develops on a Mac. Everything except live capture and the overlay window can run and be tested on macOS against recorded clips. The same replay source powers the eval harness.

## ADR-009: A cloud gateway is required before selling (Milestone 8)

**Choice:** a small hosted gateway (FastAPI on Fly.io or Cloud Run, PostgreSQL on Neon or Supabase, an auth provider, and Stripe usage-based billing) proxies model calls so provider keys never ship in the app. It meters tokens per user.

**Why:** a usage-based subscription needs server-side keys, quotas and metering. Until then, the local engine reads developer keys from OS-protected config. Keys are never stored in the frontend.

## ADR-010: Game policy gate

**Choice:** every game adapter declares `live_coaching_allowed`, `allowed_capture_modes` and its telemetry sources. The engine refuses live coaching for titles that are unknown or restricted. Riot titles are blocked from live tips.

**Launch titles:**

- **CS2:** screen reading plus Valve's official Game State Integration (a config file the game reads, with no memory access). Third-party platforms such as FACEIT run their own anti-cheat and may restrict overlays, so we treat them as unsupported for live tips until verified.
- **FromSoft-style RPG:** screen only, borderless mode. Easy Anti-Cheat doesn't object to external screen capture, but we never inject.
- **Minecraft:** screen first. An optional Fabric mod for telemetry comes later and only for single-player or servers that allow it.
