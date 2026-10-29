# Evals

Labeled gameplay moments and the harness that scores models on them (Milestone 2).

- `datasets/`: labeled cases (JSONL), committed
- `clips/`: the video files, gitignored. Never commit footage.
- `reports/`: harness output, gitignored. Copy the numbers that matter into `docs/model-selection.md`.

## Quick start (free)

```bash
npm run sample-clip   # synthetic clip at evals/clips/sample.mp4
npm run eval          # runs every dataset on the free mock provider
```

The report lands in `evals/reports/<timestamp>/report.md`, with `summary.json` and per-case `results.jsonl` next to it.

## 1. Record clips (Windows desktop)

Play in borderless windowed mode and run:

```bash
uv run gamesense-eval record --game minecraft --window "Minecraft" --seconds 180
```

This captures the game window the same way the live coach does and saves `evals/clips/minecraft_<date>_<time>.mp4`. Press **Enter** in the terminal whenever something worth coaching happens (low health, a bad buy, a boss opening). The marks are saved to a `.marks.json` file next to the clip so you can find those moments when labeling. Moments where a good coach would stay quiet matter too, so label some calm stretches as well.

Aim for about 20 cases per game: roughly two-thirds where a tip is warranted and one-third where silence is correct.

## 2. Label cases

Each case is one decision moment in a clip. The harness samples the clip from `start_s` to `end_s` at the live rate (4 fps), runs the fast path, and sends the last 2 frames exactly as the live coach would.

The easiest way to add one is the helper:

```bash
uv run gamesense-eval add-case --dataset evals/datasets/minecraft.jsonl \
  --clip minecraft_20261030_2015.mp4 --game minecraft --end 42.5 \
  --tip --obs "night|sunset" --obs "no_shelter" \
  --good "Find shelter before nightfall" --bad "Keep mining" \
  --notes "Sun is setting, player is in an open field with no bed."
```

Use `--no-tip` for moments where the coach should say nothing. Or write the JSONL by hand:

```json
{"id": "mc_night_01", "game": "minecraft", "clip": "minecraft_20261030_2015.mp4",
 "start_s": 39.5, "end_s": 42.5, "tags": [],
 "labels": {"expect_tip": true, "observations": ["night|sunset", "no_shelter"],
            "activity": "exploration", "good_tips": ["Find shelter before nightfall"],
            "bad_tips": ["Keep mining"], "notes": "Sun is setting, player in an open field."}}
```

(One case per line in the real file.) Fields:

| Field | Meaning |
| --- | --- |
| `game` | `cs2`, `fromsoft_rpg`, `minecraft` or `generic`. Picks the prompt's game profile |
| `clip` | File name inside `evals/clips/` |
| `start_s`, `end_s` | Warm-up start and the decision moment (seconds). 3 s of warm-up is plenty |
| `labels.expect_tip` | Should a good coach speak right now? |
| `labels.observations` | Facts a good coach must notice, as snake_case words. A label matches when all its words appear in a model's observation type (`health_low` matches `low_health`). Use `\|` for alternatives |
| `labels.good_tips`, `bad_tips` | Example headlines, used by the judges |
| `labels.notes` | What's happening, in plain words, for the judge and for you later |

## 3. Run a comparison

```bash
uv run gamesense-eval run --providers anthropic,google,openai,muse --judge anthropic --yes
```

- Providers are `name` or `name:model`, e.g. `anthropic:claude-haiku-5-5,google:gemini-3.5-flash-lite`. Keys come from `.env`.
- Any paid provider or judge needs `--yes`. Without it the harness prints the estimated spend and stops.
- `--max-cost` (default `$1.00`) stops the run once estimated spend, judge included, passes the cap.
- `--repeats 3` repeats every case to see how consistent a model is. `--game` and `--case` narrow the run.
- `--judge heuristic` (default) is free: it compares the tip headline with your example tips. `--judge anthropic` asks Claude Sonnet 5.5, which also sees the frames, to score usefulness (1 to 5) and groundedness. Spot-check its reasons in the report.

## What the report measures

| Metric | Meaning |
| --- | --- |
| Valid | Share of calls that returned schema-valid JSON without an error |
| Silence accuracy | Spoke exactly when the label says a coach should (tips below 0.55 confidence count as silence, like the live loop) |
| Tip recall / false alarms | Spoke when it should / spoke when it should have stayed quiet |
| Perception | Share of labeled observations the model listed |
| Useful (1 to 5), Grounded | From the judge, on shown tips only |
| p50 / p95 ms | Model latency, one call at a time |
| $/call, $/hour | Estimated from reported token use. $/hour assumes 600 calls per hour |

## Growing the dataset from real play

When you rate tips with the overlay hotkeys, the engine appends the rating and the tip's text (never frames) to `~/.gamesense/feedback.jsonl`. Tips rated not useful are good candidates for new `--no-tip` or `--bad` cases.
