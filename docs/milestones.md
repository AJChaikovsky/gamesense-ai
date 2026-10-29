# Milestones

Live tips work from Milestone 1 onward, and every later milestone makes them better. Each milestone ends with acceptance criteria that can be demonstrated.

Sizes are relative effort for one developer (S is a few days, M is about 1 to 2 weeks, L is about 2 to 4 weeks).

| # | Milestone | Size | Outcome |
| --- | --- | --- | --- |
| M0 | Foundations | S | Monorepo, contracts, CI, replay source, dev setup on Mac and Windows |
| M1 | First live tip | M | Game → capture → model → validated tip on the overlay, end to end |
| M2 | Eval harness and model bake-off | M | Labeled clips, repeatable scoring, live and deep models chosen by data |
| M3 | Coaching engine quality | L | Triggers, stale validator, ranking, cooldowns, budgets, local rules |
| M4 | Launch game adapters and knowledge | L | CS2 (GSI), FromSoft-style RPG and Minecraft at Tier 2 or above, policy gate |
| M5 | Memory and personalization | M | Session store, habit patterns, evidence-backed skill profile used live |
| M6 | Session review and dashboard | M | Post-session summary, timeline, skill profile UI, data controls |
| M7 | Product polish and packaging | M | Installer, onboarding, settings, performance budget, crash reporting |
| M8 | Cloud gateway and subscription | L | Accounts, metered model proxy, Stripe billing, quotas |
| M9 | Private beta | M | Real users, telemetry on tip usefulness, fix and tune |

Hackathon (Nov 4) target: M0 and M1 plus the CS2 GSI local rules from M4, which gives a working live demo on at least one game. Muse Spark can be routed in as the model. This is a stretch goal and is not allowed to compromise the architecture.

---

## M0: Foundations

- Monorepo layout (`apps/desktop`, `services/engine`, `packages/contracts`, `knowledge`, `evals`, `docs`)
- Python engine scaffold: uv, ruff, mypy, pytest, and a `gamesense` package with module stubs
- Contracts in Pydantic, plus JSON Schema export and TypeScript type generation
- Tauri 2 plus React, TypeScript, Tailwind and shadcn scaffold that launches the engine as a sidecar (dev mode can run it separately)
- `ReplaySource` that plays an MP4 at real-time speed into the ring buffer
- Local WebSocket with the token handshake and a `TipEvent` schema
- GitHub Actions: lint and test for Python and TypeScript, Windows and macOS runners
- `CONTRIBUTING.md` with dev setup for both machines

**Done when:** `make dev` on the Mac plays a recorded clip through the engine and the dashboard shows the engine's heartbeat events. CI is green on both platforms.

## M1: First live tip

- `WindowsCaptureSource` (Windows Graphics Capture via `windows-capture`, with `dxcam` as a fallback) targeting a chosen window
- Overlay window: transparent, click-through, always on top, one tip card with expiry, dismiss hotkey
- Fast path v0: frame-difference scene-change score and a heartbeat trigger
- `VisionModelProvider` interface plus a first adapter (Claude Haiku 5.5 or Gemini Flash-Lite), structured output to `GameState` and `CoachingDecision`
- Scheduler with at most one request in flight. Basic cooldown and duplicate suppression
- Generic game adapter (Tier 1) and a simple game detector (process name)
- Spend meter in logs, with a hard hourly cap in config

**Done when:** playing Minecraft, CS2 or the RPG in borderless mode on the Windows PC shows relevant tips on the overlay. A tip appears within about 5 seconds of a situation, there's no visible FPS drop, and nothing shows when nothing is happening. The same pipeline runs on the Mac against replays.

## M2: Eval harness and model bake-off

- Recording helper and labeling format (`evals/datasets/*.jsonl`). About 20 labeled clips per launch game
- Harness: replays clips through the engine with a pluggable provider and records outputs, latency and cost
- Scorers: perception accuracy, correct silence, groundedness and usefulness (LLM judge plus human spot-check), schema validity
- Adapters for all four providers. Run the bake-off described in [model-selection.md](model-selection.md)
- Useful/not-useful hotkeys in the overlay that write ratings for later dataset growth

**Done when:** one command produces a comparison report, and the live and deep models are chosen and recorded in `docs/model-selection.md` with numbers.

## M3: Coaching engine quality

- Trigger policy v1: scene change, HUD thresholds, telemetry events, adaptive heartbeat, budget-aware vetoes
- Stale-result validator using `valid_while` conditions
- Ranker: priority, confidence threshold, novelty, the player's chosen intensity, and a "useful over frequent" silence bias
- Delivery timing: `immediate` vs. `next_lull` (hold tips until combat ends)
- Local rule engine for deterministic tips that need no model call
- Fallback mode when the provider is down or over budget
- Prompt caching (stable prefix of instructions and game knowledge)

**Done when:** on the eval set, interruptions fall and usefulness rises compared with M1. p95 latency for model tips is 5 seconds or less. Cost per hour sits within the target in model-selection.md.

## M4: Launch game adapters and knowledge

- Adapter interface with capabilities, policy and HUD regions. A policy gate enforced in the coaching loop
- **CS2 (Tier 3):** GSI config installer and receiver (health, armor, money, round phase, bomb, weapons), buy-phase and economy rules, HUD regions
- **FromSoft-style RPG (Tier 2):** HUD regions for health, FP and stamina, boss-fight detection, a knowledge pack (general mechanics and the chosen title's bosses)
- **Minecraft (Tier 2):** HUD (hearts, hunger, hotbar), day/night and danger cues, a knowledge pack (survival progression, mobs, crafting)
- Knowledge pipeline: markdown docs with source and version, FTS5 index, retrieval in prompt assembly
- Riot and other known-restricted titles are blocked from live coaching

**Done when:** each launch game beats the generic adapter on the eval set. The policy gate is tested.

## M5: Memory and personalization

- Session persistence of observations and tips with outcomes
- Habit aggregation that needs a minimum amount of evidence across distinct situations
- Skill assessments with uncertainty, linked to evidence and recomputable
- Profile-aware prompting, where known weaknesses raise tip priority for related situations
- Coaching-preference learning (frequently dismissed tip categories get suppressed)

**Done when:** across several recorded sessions, recurring behaviors show up as habits with evidence links, and live tips visibly adapt (unit and integration tests plus a demo).

## M6: Session review and dashboard

- Post-session deep-model summary: what went well, top 3 mistakes with evidence, focus for next session
- Dashboard screens from [ui-design.md](ui-design.md): home, session review timeline, skill profile, games, settings
- Data controls: view, export and delete everything. Opt-in keyframe and clip saving

**Done when:** after a play session, the review loads in under 30 seconds and every claim links to evidence.

## M7: Product polish and packaging

- Onboarding (consent, borderless check, overlay placement test, intensity)
- Settings (hotkeys, overlay appearance, capture rate, budgets, accessibility)
- Engine packaged as a sidecar binary (PyInstaller or Nuitka). Signed Windows installer (MSI or NSIS) and auto-update
- Performance budget: engine CPU and RAM caps, measured game FPS impact on the 2080 Super
- Crash and error reporting (opt-in), structured logs

**Done when:** a fresh Windows machine goes from installer to first live tip in under 5 minutes, and the measured FPS impact is within budget.

## M8: Cloud gateway and subscription

- Gateway service: auth, per-user metered proxy to model providers, quotas and rate limits
- PostgreSQL for accounts, usage and billing records. Optional profile sync
- Stripe usage-based subscription (base plan plus a monthly token or hour allowance)
- The desktop app switches from local keys to gateway auth. Keys never ship in the app

**Done when:** a new user can sign up, subscribe, play, and see accurate usage. Exceeding the quota degrades gracefully to local rules.

## M9: Private beta

- Recruit testers across the three genres, plus at least one untested game on the generic adapter
- In-app feedback and tip-usefulness analytics (opt-in)
- Tune triggers, prompts and pricing from real data

**Done when:** testers rate a clear majority of tips useful and interruptions stay rare. Unit economics hold at the chosen price.

## Later (not scheduled)

Voice coaching, macOS support for gameplay capture, more Tier 3 integrations, a local or offline model mode, and cross-device sync.
