# Model selection

The model is configuration, not architecture (see ADR-005). This doc records current prices, rough cost estimates, and how Milestone 2 picks the models.

## Two roles

| Role | Called | Needs | Candidates |
| --- | --- | --- | --- |
| **Live** | On each local trigger (target average of one call every 5 to 10 seconds while something is happening) | Vision, low latency, structured JSON output, low cost | Claude Haiku 5.5, Gemini 3.1 / 3.5 Flash-Lite, GPT-5.6 Luna, Gemini 3.8 Flash |
| **Deep** | Session review, habit analysis, rare hard situations | Strong reasoning over long context, vision on a few keyframes | Claude Sonnet 5.5, Meta Muse Spark 1.1, Gemini 3.8 Flash / 4 Argon, GPT-5.6 Terra |

## Prices (standard API, USD per 1M tokens, checked 2026-10-29)

| Provider | Model | Input | Output | Notes |
| --- | --- | --- | --- | --- |
| Anthropic | Claude Haiku 5.5 | $0.10 | $0.50 | For prompts up to 100K tokens. Vision supported |
| Anthropic | Claude Sonnet 5.5 | $2.00 | $10.00 | |
| Anthropic | Claude Opus 5.5 | $4.00 | $20.00 | Too costly for live use |
| Google | Gemini 3.1 Flash-Lite | $0.25 | $1.50 | Image input at the same rate |
| Google | Gemini 3.5 Flash-Lite | $0.30 | $2.50 | |
| Google | Gemini 3.8 Flash | $0.75 | $3.75 | Promotional price. Doubles on Jan 1, 2027 |
| Google | Gemini 4 Argon | $2.00 | $10.00 | Promotional price. Doubles on Dec 1, 2026 |
| OpenAI | GPT-5.6 Luna | $0.20 | $1.20 | Vision support to confirm in the benchmark |
| OpenAI | GPT-5.6 Terra | $2.00 | $12.00 | |
| Meta | Muse Spark 1.1 | $1.25 | $4.25 | Public preview. API image input is sparsely documented, so confirm in the benchmark |

Sources: Anthropic pricing (via the Claude API reference), [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI pricing roundup (mem0)](https://mem0.ai/library/llms-and-models/openai-api-pricing), [Muse Spark 1.1 pricing (The Decoder)](https://the-decoder.com/metas-muse-spark-1-1-api-pricing-squeezes-openai-and-anthropic-as-the-ai-price-war-heats-up/). Prices move often, so re-check before committing to subscription pricing.

## Rough live-coaching cost per hour of play

These are estimates, not measurements. Assumptions per call: 2 frames downscaled to about 1024x576 (about 800 tokens each, though tokenization differs by provider), about 1,500 tokens of instructions, game context and recent state, and about 250 output tokens. That totals about 3,100 input and 250 output. At an average of one call every 6 seconds, that's 600 calls per hour.

| Live model | Approx. cost per call | Approx. cost per hour |
| --- | --- | --- |
| Claude Haiku 5.5 | $0.0004 | **$0.26** |
| GPT-5.6 Luna | $0.0009 | $0.55 |
| Gemini 3.1 Flash-Lite | $0.0012 | $0.69 |
| Gemini 3.8 Flash | $0.0033 | $1.96 |
| Muse Spark 1.1 | $0.0049 | $2.96 |
| Claude Sonnet 5.5 | $0.0087 | $5.22 |

A deep session review (about 50K input tokens of observations plus keyframes, about 3K output) on Sonnet 5.5 costs about $0.13 per session.

Takeaways:

1. The live role must use a cheap tier. Using a frontier model for every trigger costs 10 to 20 times more for a quality gain we haven't measured yet.
2. Our own filtering matters as much as model choice. Halving the call rate halves the bill. That's why the local change detector and telemetry triggers come first.
3. Prompt caching (stable system prompt and game knowledge first, volatile frames last) cuts input cost further on every provider that supports it.
4. For subscription pricing, a heavy player (40 hours a month) costs roughly $10 to $30 a month on cheap-tier models. Plans will need an hour or token allowance, not unlimited use.
5. Reasoning models bill thinking tokens as output. Keep thinking or effort low on the live role.

## Benchmark plan (Milestone 2)

1. **Dataset:** about 20 short clips per game (60 in total) recorded by AJ. Each has human labels: what's observable (HUD values, threats, activity) and what a good coach would say, or "stay silent."
2. **Harness:** replays each clip through the real engine, with the same triggers and the same prompt, and swaps only the provider.
3. **Metrics:**
   - Perception accuracy against labels
   - Tip usefulness and groundedness, judged by a strong model plus AJ spot-checks
   - Correct silence rate
   - p50 and p95 latency
   - Cost per hour
   - Schema-valid output rate
4. **Decision rule:** pick the cheapest live model within a few points of the best usefulness score with p95 latency under 3 seconds. Pick the deep model on review quality alone. Re-run the benchmark whenever a provider ships a new cheap tier.

## Hackathon note

The Meta AI hackathon suggests Meta models. Muse Spark 1.1 is a strong candidate for the deep role (session reviews) at $1.25 and $4.25 per 1M tokens. A hackathon build can route the deep role to Muse Spark through configuration with no code changes.
