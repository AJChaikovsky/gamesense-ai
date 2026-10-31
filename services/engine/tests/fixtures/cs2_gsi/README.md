# CS2 GSI fixtures

Each `.jsonl` file is one recorded sequence of Game State Integration payloads, one
`{"t": seconds, "payload": {...}}` object per line, in the format that
`gamesense-engine --gsi-record` writes. Tests replay them with their original timing.

The current files were written by hand to match Valve's documented GSI payload shape
(player view, competitive mode). Replace or extend them with real recordings: play a
match with `--gsi-record`, trim to the interesting round, and add the expected tips to
`test_cs2_gsi.py`. Recordings never contain the auth token.

| File | Situation | Expected tips |
| --- | --- | --- |
| `ct_forgot_armor.jsonl` | CT buys an M4 but no armor or kit, drops to 18 HP, bomb planted | armor, kit, low HP, no-kit defuse |
| `t_last_round_of_half.jsonl` | T, round 12 with $3,200, then plants | spend it all, post-plant |
| `ct_dead_spectating.jsonl` | Dead and spectating a teammate | none |
| `warmup_and_menu.jsonl` | Warmup, then in the menu during freeze time | none |
