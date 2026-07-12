# Interactive RPG response release

Status: core implementation is merged through the recorded Phase 1–11 sequence. Original-roadmap completion follow-ups remain in progress and are tracked separately from the historical phase evidence.

This release hardens the foreground RPG turn path so a player command is executed once, produces one canonical visible response, advances durable interaction continuity, and returns a bounded browser payload. Stateful mechanics remain authoritative; narration and dialogue enrich presentation only.

## Completed historical phases

| Phase | Scope | Pull request | Merge SHA |
|---|---|---:|---|
| 1 | Exactly-once foreground turn execution and terminal job guards | #1336 | `014b0caf3ac7760d816809af9b857d036eff555f` |
| 2 | Canonical narration plus NPC dialogue response contract | #1337 | `861973326a18616941224d95885ada006746eaac` |
| 3 | Compact `rpg_turn_response_v2` foreground payload | #1338 | `e24bbdd8b697f8e23217bbc83c246a8854a30f3d` |
| 4 | Monotonic interaction IDs, revisions, and durable recent history | #1339 | `3176b6759f3f8beef57cdf57332789134ee7cc14` |
| 5 | End-to-end request, persistence, and serialization tracing | #1340 | `c81f720f6903aa1677b6b16016d61af10d36eee9` |
| 6 | Checksummed append-only interaction event persistence and compaction | #1341 | `382aa58b20ac26a0f46a359d62ecbc479db724ee` |
| 7 | Grounded direct-dialogue quality policy and deterministic privacy-safe repair | #1342 | `642fc90132218223769c403e4004122ce0983a58` |
| 8 | Optimistic and incremental web transcript rendering | #1343 | `567df70d67aa7e0e62785e184c6d2df493a31eda` |
| 9 | One interaction lifecycle across authoritative resolution and deferred narration | #1344 | `6b3a029f7b2284009f1b4373db58fe39c9fec8b6` |
| 10 | Permanent provider-free structural release gates | #1345 | `635cdbd181da12cad06d87cc9346806ef4edcd37` |
| 11 | Release evidence, local live-provider validation, rollout, and rollback runbook | #1346 | `8b11adfda8aedb40a6aad11f4125a010f14aa1bb` |

The machine-readable historical Phase 1–11 evidence index is in `src/app/rpg/release_finalization.py`. It records what merged; it does not assert that every item in the original roadmap is finished.

## Phase 0 reproducible baseline

The provider-free Rusty Flagon benchmark is documented in `docs/rpg-interactive-turn-performance-baseline.md` and implemented at:

```text
src/tests/rpg/performance/foreground_turn_benchmark.py
```

It executes one deterministic Bran business dialogue plus an idempotent replay and records apply-turn, provider-boundary, session load/save, job-transition, interaction, simulation, payload-size, serialization, and browser-visible response evidence. It uses a deterministic provider stub and does not contact an LLM.

## GitHub Actions policy

GitHub Actions must remain provider-free. Required checks are:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`
- `Live Chat hardening gates`

The deterministic suite may use fakes, monkeypatches, SQLite, local files, and static payloads. It must not call a live LLM, LM Studio, OpenRouter, OpenAI-compatible provider, or any external model endpoint.

The local live smoke harness contains a hard CI guard and requires an explicit operator opt-in. Do not add it to a GitHub Actions workflow.

## Local live-provider validation

Run the gateway and configured local provider first. Use an existing RPG session ID, then run from the repository root:

```powershell
$env:PYTHONPATH = "src"
$env:OMNIX_RPG_LIVE_SMOKE = "1"
python scripts/rpg_interactive_live_smoke.py --session-id "<session-id>"
```

Optional flags:

```powershell
python scripts/rpg_interactive_live_smoke.py `
  --base-url "http://127.0.0.1:8000" `
  --session-id "<session-id>" `
  --command "I ask Bran how business is doing." `
  --command "I ask Bran how his day is going." `
  --timeout-seconds 120
```

The harness sends stable `X-Omnix-Rpg-Submission-Id` values, repeats the first submission to verify idempotency, validates the compact response gates, records response bytes, and reports mean, median, p95, and maximum latency. It exits unsuccessfully when a structural gate or latency target is missed. It does not mutate GitHub Actions or upload live-provider content.

## Operator acceptance criteria

Repository gates are necessary but do not prove local provider quality or latency. Before wider use, capture local operator evidence showing:

1. Three distinct commands produce three distinct interaction IDs.
2. Replaying the same submission ID returns the original interaction ID and does not execute a second turn.
3. Every response uses `rpg_turn_response_v2`, has visible text, and remains at or below 50,000 bytes.
4. Dialogue shows the addressed NPC line, not only generic scene prose.
5. A reload preserves recent interactions and pending/completed narration lifecycle state.
6. A stateful command changes only authoritative domains and deferred narration does not rewrite mechanics.
7. Median foreground dialogue latency is 1.5 seconds or less on the intended local provider and hardware.
8. p95 foreground dialogue latency is 2.5 seconds or less on the intended local provider and hardware.

Latency and provider-quality targets are operator evidence, not provider-free CI assertions.

## Staged rollout

### Stage 1 — single-session canary

Use one disposable or backed-up session. Run the local smoke harness and inspect `resources/data/logs/rpg/*.jsonl` for the shared trace ID, response size, persistence spans, and duplicate execution warnings.

### Stage 2 — continuity and reload

Run at least ten dialogue interactions with one NPC, reload the session, and verify the timeline, interaction sequence, and dialogue continuity. Include one repeated question to confirm non-identical continuity handling.

### Stage 3 — mixed mechanics

Exercise trade, travel, combat, inventory, and quest actions. Confirm each authoritative change appears once and narration lifecycle updates the existing interaction rather than creating a duplicate transcript entry.

### Stage 4 — extended local soak

Run the existing provider-free 1000-turn deterministic endurance gate in CI and a separate local provider-backed conversational soak. Keep the provider-backed soak local. Record latency and quality summaries without committing private prompts, provider responses, secrets, or session payloads.

## Rollback

1. Stop new turn submissions before changing code.
2. Back up the session JSON and adjacent `.interactions.jsonl` files.
3. Revert phase merge commits in reverse order, starting with the newest affected phase. Do not delete append-only interaction logs during rollback.
4. Restart the gateway and load the backed-up session. Older snapshots remain authoritative; event replay is additive and checksum-validated.
5. Run provider-free deterministic gates on the rollback branch.
6. Run a short local smoke only after the rollback build is stable and only outside CI.

A rollback must not manually edit authoritative mechanics, interaction IDs, submission IDs, or job terminal states.

## Data and privacy posture

- Full session and runtime graphs are excluded from foreground responses.
- Private NPC biography and private inventory are not valid presentation grounding.
- Local live-provider evidence may contain user or story content; keep it outside source control.
- Structured diagnostics should retain IDs, timings, sizes, statuses, and bounded summaries rather than full prompts or raw private state.
