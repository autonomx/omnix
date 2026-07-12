# Interactive RPG response release

Status: original-roadmap implementation is complete through PR #1355, subject to provider-free CI on its exact head. Provider-, hardware-, and browser-specific acceptance evidence remains an explicit local operator run and is never executed in GitHub Actions.

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

The machine-readable historical Phase 1–11 evidence index is in `src/app/rpg/release_finalization.py`. It records what merged; it does not substitute for the completion follow-ups below.

## Original-roadmap completion follow-ups

| Scope | Pull request | Merge SHA / status |
|---|---:|---|
| Deterministic Phase 0 baseline and original 1.5s / 2.5s targets | #1348 | `e14eed6a14d632afba33b1ee8de909a14b70fc5e` |
| Durable cross-process submission ownership | #1349 | `5b4e39b140115817664d10c6450970fe18087579` |
| Safe abandoned-owner recovery before execution | #1350 | `19f1e02199cb83b6764f09db69252c3c88743941` |
| Runtime UTF-8 50KB response ceiling | #1351 | `17eb5d6f48a8879a95282f1845eb8c6de0701d05` |
| Canonical response cleanup and duplicate route removal | #1352 | `3e26b13c862d17241e3807232e0c8434167afa32` |
| Full-path attribution, CPU/RSS, provider-stage, and response telemetry | #1353 | `24340aa47c426c4a0aaa6e4c24c606edb61726bc` |
| Interaction-keyed UI reconciliation and browser diagnostics | #1354 | `96c350b6bc7da445aeb894e681017bf7fa309bea` |
| Save migration, expanded quality matrix, final gates, and local evidence bundle | #1355 | current completion PR; exact merge SHA is recorded after merge |

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

The deterministic suite may use fakes, monkeypatches, SQLite, local files, static payloads, and static timing dictionaries. It must not call a live LLM, LM Studio, OpenRouter, OpenAI-compatible provider, or any external model endpoint.

The local live smoke and dialogue-quality harnesses contain hard CI guards and require an explicit operator opt-in. Do not add either harness to a GitHub Actions workflow.

## Local live-provider validation

Run the gateway and configured local provider first. Use an existing RPG session ID, then run from the repository root:

```powershell
$env:PYTHONPATH = "src"
$env:OMNIX_RPG_LIVE_SMOKE = "1"
python scripts/rpg_interactive_live_smoke.py --session-id "<session-id>" `
  > resources/data/test-results/rpg-live-smoke.json
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

The smoke harness sends stable `X-Omnix-Rpg-Submission-Id` values, repeats the first submission to verify idempotency, validates compact response gates, records provider-call count, provider time, non-provider overhead, final server attribution, trace ID, response bytes, and mean/median/p95/maximum latency. It exits unsuccessfully when a structural or live runtime target is missed.

Use a disposable or backed-up session with Bran present to produce the live dialogue-quality report:

```powershell
python scripts/rpg_interactive_live_dialogue_quality.py `
  --base-url "http://127.0.0.1:8000" `
  --session-id "<session-id>" `
  --timeout-seconds 120 `
  --output resources/data/test-results/rpg-live-dialogue-quality.json
```

This local-only runner submits the complete accepted scenario matrix, verifies exactly one provider call per response, evaluates directness, speaker correctness, grounding, continuity, repetition, leakage, and empty-line rates, and exits nonzero when the original quality thresholds are missed. It does not submit the intentionally bad candidate fixtures used by provider-free CI.

## Complete local acceptance bundle

Export at least three browser timing snapshots from the developer diagnostics drawer. Enable the drawer in a local build or with `?rpgDiagnostics=1`, then use **Copy diagnostics JSON** and save the clipboard contents as `rpg-browser-timing.json`. Keep private story content outside source control.

Prepare:

- the live smoke report;
- the live-provider dialogue-quality report from `rpg_interactive_live_dialogue_quality.py`;
- the browser JSON object containing a `samples` list with interaction IDs and client timing fields.

Then run:

```powershell
python scripts/rpg_interactive_local_acceptance.py `
  --live-smoke-report resources/data/test-results/rpg-live-smoke.json `
  --dialogue-quality-report resources/data/test-results/rpg-live-dialogue-quality.json `
  --browser-timing-report resources/data/test-results/rpg-browser-timing.json `
  --output resources/data/test-results/rpg-local-acceptance.json
```

This validator exits nonzero unless all three evidence surfaces pass.

## Operator acceptance criteria

Repository gates are necessary but do not prove local provider quality or latency. Before wider use, capture local operator evidence showing:

1. Three distinct commands produce three distinct interaction IDs.
2. Replaying the same submission ID returns the original interaction ID and does not execute a second turn.
3. Every response uses `rpg_turn_response_v2`, includes top-level `interaction_id` and `interaction_seq`, has visible text, and remains at or below 50,000 UTF-8 bytes.
4. Each dialogue performs exactly one provider call.
5. Foreground child spans explain at least 95% of request wall time.
6. Non-provider HTTP overhead is at most 250ms.
7. Browser React commit-to-visible time is at most 50ms.
8. Direct-answer rate is at least 95%; correct-speaker rate is at least 99%; grounded-specificity rate is at least 90%; continuity rate is at least 95%.
9. Near-duplicate rate is below 5%; private-leak and empty-line rates are zero.
10. A reload preserves migrated recent interactions, monotonic sequence/revision, and pending/completed narration lifecycle state.
11. A stateful command changes only authoritative domains and deferred narration does not rewrite mechanics.
12. Median foreground dialogue latency is 1.5 seconds or less on the intended local provider and hardware.
13. p95 foreground dialogue latency is 2.5 seconds or less on the intended local provider and hardware.

Latency, provider quality, and browser timing targets are operator evidence, not provider-free CI assertions.

## Staged rollout

### Stage 1 — single-session canary

Use one disposable or backed-up session. Run the local smoke harness and inspect `resources/data/logs/rpg/*.jsonl` for the shared trace ID, response size, persistence spans, attribution percentage, provider timing, and duplicate execution warnings.

### Stage 2 — continuity and reload

Run at least ten dialogue interactions with one NPC, reload the session, and verify the timeline, interaction sequence, and dialogue continuity. Include one repeated question to confirm non-identical continuity handling.

### Stage 3 — mixed mechanics

Exercise trade, travel, combat, inventory, and quest actions. Confirm each authoritative change appears once and narration lifecycle updates the existing interaction rather than creating a duplicate transcript entry.

### Stage 4 — extended local soak

Run the provider-free 1000-turn deterministic endurance gate in CI and a separate local provider-backed conversational soak. Keep the provider-backed soak local. Record latency and quality summaries without committing private prompts, provider responses, secrets, or session payloads.

## Rollback

1. Stop new turn submissions before changing code.
2. Back up the session JSON and adjacent `.interactions.jsonl` files.
3. Revert completion and phase merge commits in reverse order, starting with the newest affected change. Do not delete append-only interaction logs during rollback.
4. Restart the gateway and load the backed-up session. Older snapshots remain authoritative; event replay is additive and checksum-validated.
5. Run provider-free deterministic gates on the rollback branch.
6. Run a short local smoke only after the rollback build is stable and only outside CI.

A rollback must not manually edit authoritative mechanics, interaction IDs, submission IDs, or job terminal states.

## Data and privacy posture

- Full session and runtime graphs are excluded from foreground responses.
- Private NPC biography and private inventory are not valid presentation grounding.
- Local live-provider evidence may contain user or story content; keep it outside source control.
- Structured diagnostics should retain IDs, timings, sizes, statuses, and bounded summaries rather than full prompts or raw private state.
