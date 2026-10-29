# Architecture

This doc turns AJ's Product Architecture v0.1 into an implementation-ready plan, using the decisions in [decisions.md](decisions.md). The product principles still hold:

- The architecture is universal, but expertise varies by game.
- Useful advice beats frequent advice.
- The player stays in control.

## Process layout

Everything runs on the player's PC. A cloud gateway is added at Milestone 8.

```
┌──────────────────────── Player's Windows PC ────────────────────────┐
│                                                                     │
│  Game (borderless/windowed)          CS2 GSI ──HTTP POST──┐         │
│        │ Windows Graphics Capture                         │         │
│        ▼                                                  ▼         │
│  ┌─────────────────── Python engine (child proc) ─────────────────┐│
│  │ capture ─► ring buffer ─► fast path (diff, HUD OCR, telemetry)  ││
│  │                               │ trigger                         ││
│  │                               ▼                                 ││
│  │   coaching orchestrator ◄── knowledge (FTS5) ◄── memory (SQLite)││
│  │        │ provider interface ──────────────► cloud model APIs    ││
│  │        ▼                                                        ││
│  │   validator ─► ranker / cooldown ─► WebSocket                   ││
│  └────────────────────────────────────────┬────────────────────────┘│
│                                           │ ws://127.0.0.1 (token)  │
│  ┌─────────── Electron app (TS + React) ──▼────────────────────────┐│
│  │  overlay window (click-through)   dashboard window   tray       ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

- The Electron main process starts the engine as a child process and stops it on exit.
- The engine binds only to `127.0.0.1` on a random port, with a per-launch auth token passed to the frontend. No other process can talk to it.
- The engine works headless too, which is how it runs on macOS against replays and in the eval harness.

## Engine modules (`services/engine/gamesense/`)

| Module | Owns | Must not |
| --- | --- | --- |
| `capture/` | `CaptureSource` interface, `WindowsCaptureSource`, `ReplaySource`, frame ring buffer (last ~60 s, downscaled) | Interpret frames |
| `telemetry/` | Official telemetry adapters (CS2 GSI receiver, later the Minecraft mod bridge) | Read game memory |
| `perception/` | Fast path (frame diff, HUD region crops, OCR, scene-change scores), builds `GameState` from local signals plus model output | Decide strategy |
| `coaching/` | Trigger policy, request scheduler (at most one in flight per session), prompt assembly, stale-result validator, ranking, cooldown and dedup, delivery decision | Render UI |
| `providers/` | `VisionModelProvider` interface plus Anthropic, Google, OpenAI and Meta adapters, budgets, retries and timeouts | Hold game logic |
| `knowledge/` | Game packs (genre and game docs), FTS5 retrieval | Track the player |
| `memory/` | Short-term buffer, session store, long-term profile, habit aggregation | Store raw frames by default |
| `games/` | Game adapters (detection, capability and policy declaration, HUD regions, knowledge pack id) | Bypass the policy gate |
| `api/` | FastAPI and WebSocket server, event schema | Contain business logic |
| `storage/` | SQLite repositories and migrations | Leak SQL outside the repositories |

## The live loop

```
every tick (configurable, default 4 Hz on the fast path):
  frame ← capture.latest()
  signals ← fast_path(frame, telemetry)          # ms, local
  short_term.append(signals)
  if trigger_policy.should_analyze(signals, short_term, budget):
      if scheduler.idle():                        # ≤1 request in flight
          ctx ← assemble(frames[-2:], short_term, knowledge, profile)
          scheduler.submit(provider.analyze(ctx))  # async, non-blocking

on model result (state, decision?):
  if validator.still_valid(decision, short_term.now)   # situation unchanged?
     and policy.allows_live(game)
     and cooldown.ok(decision) and ranker.passes(decision):
        ws.send(TipEvent(decision))
  memory.record(state, decision, delivered=…)
```

**Triggers** are a mix of the following:

- A scene-change score above a threshold
- A telemetry event (round start, low health, bomb planted)
- A HUD value crossing a threshold (health dropping, inventory full)
- A periodic heartbeat (for example, every 20 seconds during activity), so slow-burn situations still get looked at

The budget tracker can veto triggers when the hourly spend cap is near.

**Two latency targets** (design goals to verify by benchmark):

- Rule-based local tips (for example, a CS2 GSI "low HP, not buying armor" tip) appear within 1 to 2 seconds.
- Model-generated tips appear within 3 to 5 seconds, end to end.

**Fallback:** if the provider fails or the budget runs out, local rule-based tips keep working and the status dot turns red. Gameplay is never affected.

## Data contracts (`packages/contracts`)

These are the v0.1 contracts, with fields added for traceability.

```python
class Observation(BaseModel):
    type: str                 # "health_low", "enemy_visible", …
    value: Any
    confidence: float         # 0–1, model/heuristic estimate, not calibrated
    source: Literal["visual", "ocr", "telemetry", "model", "rule"]
    kind: Literal["observed", "inferred"]

class GameState(BaseModel):
    game_id: str; genre: str; session_id: str; timestamp: datetime
    activity: str | None                # "exploration", "combat", "buy_phase", …
    observations: list[Observation]
    unknowns: list[str]
    game_specific: dict[str, Any] = {}  # adapter-defined extension
    frame_refs: list[str]               # ring-buffer ids, for evidence

class CoachingDecision(BaseModel):
    id: str; category: str; action: str
    message: str                        # ≤ 8 words headline
    detail: str | None
    priority: Literal["info", "important", "urgent"]
    confidence: float
    delivery: Literal["immediate", "next_lull", "post_session"]
    expires_in_seconds: int
    valid_while: list[Condition]        # checked by stale-result validator
    evidence: list[str]                 # observation ids that justify it

class HabitObservation(BaseModel):
    skill: str; behavior: str; session_id: str
    evidence: list[str]                 # observation/tip ids
    evidence_count: int; confidence: float
```

`valid_while` is what makes the stale-result validator possible. A tip like "heal before engaging" carries `health < 40%` and `activity != combat`. If either stops being true by the time the result arrives, the tip is dropped.

## Memory

| Layer | Storage | Lifetime |
| --- | --- | --- |
| Short-term | In-process ring of `GameState` and signals | Last 30 to 60 seconds |
| Session | SQLite: `game_session`, `observation`, `coaching_tip` (with outcome: delivered, dismissed, rated, expired) | Kept until the user deletes it |
| Long-term | SQLite: `habit_pattern`, `skill_assessment`, each linked to evidence rows | Recomputable from the session data |

The other entities from v0.1 are `player_profile`, `game` and `knowledge_document`. Skill assessments are always derived from evidence, so they can be recomputed or challenged. A single death is never treated as proof of a habit. A pattern needs a minimum evidence count across separate situations.

## Game adapters

```python
class GameAdapter(Protocol):
    game_id: str; genre: str; tier: Literal[1, 2, 3]
    def detect(self, process_name: str, window_title: str) -> bool: ...
    capabilities: Capabilities   # capture modes, telemetry sources, hud_regions
    policy: GamePolicy           # live_coaching_allowed, notes, verified_on
    knowledge_pack: str | None
    rules: list[LocalRule]       # cheap deterministic tips (fast path)
```

There's a generic adapter for any unrecognized game (Tier 1, live coaching allowed only after the user confirms the game permits it). The launch adapters are `cs2` (Tier 3, GSI), `fromsoft_rpg` (Tier 2) and `minecraft` (Tier 2, Tier 3 later).

## Privacy and security

- Capture starts only after explicit consent per game. Frames go to the cloud model only for triggered analyses, downscaled, and are never stored by default.
- Saving clips is opt-in. The dashboard can show, export and delete all stored data.
- Provider keys live in the OS credential store (Windows Credential Manager or macOS Keychain) for development, and on the gateway for commercial builds. Keys never enter the frontend.
- GameSense never injects, reads memory, sends inputs or interacts with anti-cheat.

## Evaluation built in

`evals/` holds clip manifests and labels (clips themselves live outside git), a harness that runs the engine in replay mode, and a report generator. Useful/not-useful hotkey ratings from real play feed back into the dataset. Every model or prompt change runs the eval before merge (see Milestone 2).
