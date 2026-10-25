# Omnix RPG Production Roadmap

**Revision 5, 2026-10-23. Status: approved by independent review (four passes) and by the owner (§7); in implementation, see §11.** This plan takes the RPG from where the 2026-10-23 evaluation found it to
production quality: every scorecard area at **Strong** or better, measured by the gates in §6. Work packages are
`RQ-<phase>.<n>`. Review history is in §10.

## Contents

1. Goal
2. Scorecard: baseline and targets
3. Facts the plan rests on
4. Target architecture
5. Phases and work packages
6. Gate set
7. Owner questions
8. Risks
9. Out of scope
10. Review log

## 1. Goal

A player picks any launch-ready world (a bundled one, a community one, or one they made), starts a campaign and plays
it for 200 turns or three hours without meeting a state bug: what the screen says happened is what the saved game
records. Common turns show their first words within about two seconds, and grid moves feel immediate. The world
changes while they play and while they are away, in ways they can notice and affect. Fights, trade, quests and
progression have stakes and choices. The play screen is made for a player, not a developer. Saved campaigns survive
every upgrade, on the operator's database and on desktop installs.

Underneath, every state change is a turn through one typed pipeline: a typed command, a button, a map action, a
tactical move, an idle catch-up. Rules decide what happens, including what a character says they offer, and resolve it
into typed state changes. One reducer applies them and the world ticks. The turn commits once, marking its narration
pending, and the narrator then phrases the committed outcome into an immutable narrative response. A new mechanic is added by
adding one resolver, and cannot silently undo another.

What does not change:
- the seven bounded contexts and AL017;
- the persistence model: snapshots, per-turn JSON patches, state hashes, upcasters and retention;
- an atomic turn commit; it now records the narration as pending, and the immutable narrative response is written
  once the narration is final;
- seeded dice and durable jobs;
- the generated web contract;
- the rule that the model proposes and deterministic Omnix code decides.

## 2. Scorecard: baseline and targets

Grades:
- **Weak:** known defects in normal play.
- **Fair:** works on the tested path.
- **Strong:** meets every measurable target below, gated.
- **Excellent:** Strong, plus the stretch target.

**Turn path** means the module list RQ-0.7 records: the modules the playthrough suite executes inside a turn. It is
stored in `resources/architecture/layers.toml` as `[rpg_turn_path]` and refreshed when a phase closes. Baselines
marked † are hand counts from the evaluation; RQ-0.1 replaces them with the scorecard script's output, which
publishes its exact patterns.

| # | Area | Baseline (2026-10-23) | Strong target (gate) | Stretch (Excellent) |
|---|------|-----------------------|----------------------|---------------------|
| A1 | Architecture between contexts | Strong: AL017 = 0 | AL017 = 0, and the count of cross-context imports that bypass a `contracts` module is ratcheted (it may only shrink; baseline from RQ-0.1) | Contract-only imports enforced for all contexts |
| A2 | Architecture inside the turn | **Weak.** Untyped state: 132 `simulation_state` and 144 `runtime_state` keys read by string†. Three live nested `apply_turn` layers over 13 inner stages. 34 save call sites in 22 modules†. The turn result is copied to four nesting levels. Seven state-changing entry points sit outside the turn pipeline (§3). | Every state-changing entry point is a turn kind through one pipeline (§4.1). Typed campaign state for every section the turn path touches. Lint, baseline 0: one save per turn, and state mutation only in the reducer. `TurnOutcome` is the only turn result. No string-key state reads in the turn path (lint, baseline 0). | All state sections typed, including genesis-owned ones |
| A3 | Mechanic ownership | **Weak.** Three combat paths (combat runtime, the session's older engine, tactical attack). Two inventories. A starter-town merchant fallback. Two NPC routine systems. | One owner module per mechanic (§4.3), checked by a registry test | — |
| A4 | Content in code | **Weak.** Starter-town names in engine code: "Bran" 158 hits in 46 files†; Rusty Flagon in 29 modules | Zero world-specific names in `rules`, `world`, `session`, `narration` outside test fixtures (lint); the starter town and demo are bundled worlds | — |
| P1 | Persistence and recovery | Strong | Keep, and add: a crash-mid-turn test (RQ-8.5); document-version and pinned columns, with the upcast as its own revision (RQ-1.1); every operator and desktop campaign upgraded with a pinned pre-upgrade snapshot; newer documents refused (RQ-1.7) | Campaign export and import (RQ-8.6) |
| M1 | Mechanics correctness | **Fair.** All fixed in the last two days from live play; no published-world playthrough test | Playthrough suite (RQ-0.3) passes 100% on three worlds; published-world golden (RQ-0.2) matches | Model-driven autoplay finds no state defect in 3 × 500 turns |
| M2 | Intent understanding | **Weak.** 83 word lists† in turn-path packages; substring defects ("useful", "forest", "white") | On the frozen held-out set (RQ-0.4: 1,200 inputs, at least 800 not stateful and at least 700 with a target entity), Wilson 95% bounds: action family lower ≥ 0.95, target entity lower ≥ 0.95, false stateful upper ≤ 1.0% | Lower bounds ≥ 0.97; no false stateful action among ≥ 800 (upper bound ≤ 0.5%) |
| G1 | Gameplay depth | **Weak.** A lost fight costs a tenth of max HP and ends the fight. Quests advance only by reaching places. No undo or save points. | RQ-5.1–5.4 and RQ-5.7 built per their approved design notes, each with playthrough scenarios. The balance simulation stays inside its bands. Owner playtest rubric (RQ-5.0) averages ≥ 4/5 on stakes, choice and progression. | RQ-5.5 and RQ-5.6 too; rubric ≥ 4.5/5 |
| W1 | Evolving world | **Weak.** Published-world NPCs have no routine or goal, and the pressure clock is not bootstrapped for published worlds | A scripted 200-turn Aurelia run with idle gaps: every named NPC has a routine; at least one pressure transition per 50 turns; at least one player-visible world event per 20 turns; who is present changes with time of day; returning after idle time lists only real changes; the run replays to identical `state_hash_after` (document, including NPC places and routine cursors) and `maps_hash_after` (grid cells) | Off-screen region simulation; player actions measurably shift pressures |
| D1 | Determinism | Strong in core. Unseeded `random` in three modules; `uuid4` ids and wall-clock time in the quest, choice and causal-memory models | No unseeded randomness, `uuid4` or wall-clock read reachable from the turn path (AL013 scope covers the turn path); 1,000-turn replay identical | — |
| F1 | Latency (reference model, §7 Q-5) | Look 22 s, arrive 8 s, question about 3 s, fight 9–14 s (Claude CLI, from commit notes) | 20 runs per turn class per provider. Outcome card p95: ≤ 300 ms for tactical moves and attacks, ≤ 1.0 s for other grammar-parsed and structured turns, ≤ 3.0 s for turns that need an intent call. First narration visible p95 ≤ 2.5 s. Complete turn p50 ≤ 6 s, p95 ≤ 10 s. Deterministic turns (status, equip, inventory, wait) ≤ 500 ms complete, with no model call. | Outcome ≤ 0.5 s, first narration ≤ 1.5 s, complete p95 ≤ 7 s |
| F2 | Turn overhead without model time | p95 296 ms at 100 KB, 352 ms at 1 MB (budget 150 ms); 44 SQL statements per turn. Measured at `31ff66f834` over 30 turns | 200 turns per size. Player turns: p95 ≤ 150 ms at 1 MB and at most 20 statements. World-tick turns: p95 ≤ 500 ms for a catch-up of up to 24 in-game hours. Saved state ≤ 1 MB after 1,000 turns. | Player turns p95 ≤ 100 ms |
| F3 | Model calls per turn | 3.4 on 2026-10-15; fewer since, not re-measured | Over the latency harness's turn mix: at least 80% of turns make at most one call, deterministic turns make none, and no turn makes more than two | — |
| U1 | Play screen | **Fair.** The Hermes job panel always renders. Two stubbed Hermes panels still run their queries. Job-queue wording. Turns, drafts, sessions and the map are polled. | Player-first layout with developer panels behind Developer mode (RQ-7.1). Outcome card before narration. SSE turn stream. One campaign-creation flow. axe: 0 serious or critical. At 360 × 740 px, no horizontal scroll and every core task (RQ-7.7) completes in Playwright. Keyboard-only play. The owner completes every core task without help. | — |
| U2 | Web code health | **Fair.** `rpgUiState.ts` 1,324 lines, `RpgLoadoutTabs.tsx` 1,196, `RpgWorkspace.tsx` 959, `RpgActionComposer.tsx` 734; 48 CSS files with layered "Design"/"Polish" sheets | No RPG web source file over 600 lines (the generated contract excepted); one stylesheet per component; play-screen screenshots in light and dark at 360, 768 and 1,440 px | — |
| N1 | Narration quality (new) | Not measured for published worlds; a dialogue benchmark exists for the starter town | Eval over 900 narrated turns, 300 per world, at least 600 with a speaker (RQ-0.6). Wilson bounds: state contradictions upper ≤ 2.0%; correct speaker lower ≥ 0.985; grounded in canon lower ≥ 0.93 (judge calibrated, RQ-0.6). Near-duplicate rate ≤ 5%. | Contradictions upper ≤ 1.3% |
| S1 | Trust and safety (new) | Bundles are size-limited and hash-checked; SVG assets are accepted; world text reaches prompts unlabelled | World text delimited as untrusted data in prompts, with an injection corpus that changes no state and leaks no private canon (RQ-8.1). Bundle SVGs sanitized or rasterized, and asset routes served with a restrictive CSP (RQ-8.7). Per-user model budget (RQ-8.2). Tenant-isolation tests (RQ-8.3). A retention policy (RQ-8.10). | — |
| O1 | Operability (new) | Per-turn traces and degraded-stage logs exist | Over the playthrough suite and autoplay runs: turn failure ≤ 0.5%, and the degraded-stage rate reported. Operations shows latency per turn class, failures and model cost per turn from live use (RQ-8.4). Provider outage and timeout behaviour defined and tested (RQ-8.8). A crash mid-turn leaves no partial turn (RQ-8.5). | Alerts on the error budget |
| T1 | Tests as a safety net | Python: 1,330 pass, 4 skip, and 8 fail instead of skipping without a database URL. Web: 258 pass. Live play found every recent bug. | Every harness in §6 exists and is in the gate set, run locally before each phase closes | — |

## 3. Facts the plan rests on

Checked against `rpg-evolve` at `ce84e4787e` on 2026-10-23, and by two independent review passes (§10).

**Size.**
- `src/app/apps/rpg` is 270,526 lines in 1,109 Python files: genesis 74,200, session 58,212, narration 50,724,
  world 32,788, rules 27,429, edge 15,503, foundation 11,223.
- The web feature is about 21,000 hand-written TypeScript lines, plus `api/generated.ts` (14,066) and 11,924 CSS
  lines in 48 files.
- RPG tests: 289 Python files (45,343 lines) and 70 web test files.
- RPG migrations live in `src/app/apps/rpg/migrations` (latest 0159).

**The interactive turn today.** The outer pipeline is `session/pipeline.py`: `fast_visible_dialogue → resolve →
fast_combat_result → dialogue_quality → visible_response → player_agency → interaction_commit →
interaction_lifecycle`. Under PostgreSQL, saves are deferred to the commit stage. Inside `resolve`:

1. `interactive_first_call_runtime._apply_turn_core` chooses among four paths: a safe dialogue fallback, a service
   match, the first-call action and semantic advisories, or the stateful runtime.
2. `turn_response_composition.apply_turn` binds the seed and clock, then canonicalizes the publication, persists
   "soft truth" and advances the causal runtime.
3. `player_turn_execution.apply_turn` (967 lines) counts the turn, handles companion acceptance and other early
   returns, and calls `_apply_turn_authoritative`. Of the early returns, two save through
   `_sync_session_simulation_state_for_early_return` (`:314`, `:705`) and one calls `save_session` directly (`:607`).
4. `turn_authoritative_guards` patches semantic direct responses and service postconditions around
   `turn_apply._apply_turn_authoritative_base`.
5. That runs 13 stages (`_TURN_APPLY_STAGES`), three of them mechanical `_continued_1` splits.

`turn_authoritative_guards.apply_turn` (`:687`) has no caller; only its helpers are used. Every stage loads the
turn-start session, so a change made outside the authoritative stage is lost unless that stage applies it again. That
is the root of most of the 2026-10-22/23 fixes.

**Commit and narration storage.**
- **Atomic commit.** `session/persistence/rpg_turn_service.persist_foreground_turn` atomically commits the campaign,
  turn, interaction, canon, job, submission and the canonical narrative response (`_canonical_narrative_response`,
  `:53`). This is checked by `src/tests/persistence/test_rpg_narrative_atomic_turn_integration.py`.
- **Concurrency.** Optimistic concurrency on the campaign revision is in `foundation/persistence/rpg_repository.py`.
- **Deferred narration.** `session/narration_jobs.py:153` writes the finished narration into
  `runtime_state.narration_artifacts` and calls `save_runtime_session`. Outside a turn, that save advances the
  revision without a turn row (`session/persistence/session_records.py:121-142`).
- **Who reads the artifacts.** Today the narrator's continuity builder reads `runtime_state.narration_artifacts`
  (`_build_recent_narration_continuity`, `session/semantic_state_changes.py:768`). Writers include
  `semantic_response_projection.py:402-428`, `companion_turn_runtime.py:487-499` and `turn_bound_narration.py`. The
  web client does not read it.
- **Narration tables:**
  - `omnix_rpg_narrative_responses` (RPG migration 0020): immutable canonical responses, `content_hash` and
    `canonical_jsonb` `NOT NULL`, one row per `(workspace_id, campaign_id, turn_id)`.
  - `omnix_rpg_narrative_deliveries` (0022): mutable delivery cursors for those responses.
  - `omnix_rpg_narration_events` (platform migration 0104): a transport table with a retention policy, a 64 KB
    payload cap and no `workspace_id`.
- **Locks.** `persist_foreground_turn` locks the submission row `FOR UPDATE`; `commit_turn` locks the campaign row.
  Both locks are taken at commit time only. The PostgreSQL `lock_timeout` is 5 s (`persistence/config.py:28`).
- **Hermes** runs its turns with `narration_mode: "blocking"` (`canonical_submitter.py:37`).
- **Map positions.** Grid positions live in `omnix_rpg_campaign_map_instances.snapshot_jsonb` (RPG migration 0023),
  outside the campaign document. NPC spatial goals move NPCs by cell (`move_to_cell`).

**Turn rows and snapshots.**
- **Turn rows.** A turn row's `schema_version` holds the session's `save_version` (default `"rpg-session-v1"`,
  `session_records.py:77`), or `"tactical-spatial-v1"` for tactical commands. It does not hold the campaign document
  version.
- **Snapshots** are unique per `(campaign_id, revision)` (RPG migration 0006, line 73). They are taken every 20
  revisions (`OMNIX_RPG_SNAPSHOT_EVERY`, `rpg_turn_service.py:18`). Retention keeps the newest 20 and every 100th
  revision (`declarations.py:33-59`).
- **Revisions without patches.** Out-of-turn saves produce revisions without a patch.

**Other state-changing entry points** (not through the interactive pipeline):

| Entry point | Where | Writes and concurrency |
|-------------|-------|------------------------|
| `POST /api/rpg/map-instances/{id}/tactical/move`, `/tactical/attack` | `world/tactical_spatial_service.py` | Commits a campaign revision and map events itself (`work.rpg.commit_turn`, `:92`). Needs both `expected_campaign_revision` and `expected_map_state_revision` (`:155-168`). Answers synchronously with its own idempotent response. |
| `POST /api/rpg/sessions/{id}/loadout-action` | `session/loadout.py` | Equipment |
| `POST /api/rpg/sessions/{id}/maps/{map}/map-actions` | `world/map_actions.py` | Map state |
| `POST /api/rpg/campaigns/{id}/spatial-ticks` | `world/npc_spatial_campaign_runtime.py` | Locks the campaign; its token is `expected_world_tick` (`:650`). Writes `omnix_rpg_campaign_spatial_clocks`, `omnix_rpg_npc_spatial_goals`, `_routines`, `_transitions` and `_tick_runs` (RPG migration 0027). None of these rows is in the hashed document. |
| `POST /api/rpg/sessions/{id}/continue` | session routes | Session state |
| Hermes direct turns | `edge/hermes/canonical_submitter.py:29` | Calls `interactive_first_call_runtime.apply_turn` with `session_override`, not a job keyed by `submission_id` |
| Idle and ambient ticks | `session/idle_narration_delivery.py:219,280`, `ambient_tick_runtime.py` | `save_runtime_session` |

RQ-0.8 completes this inventory over every mutating RPG route.

**State and versions.**
- **Campaign document:** typed envelope `session/campaign_state.py`, `CURRENT_SCHEMA_VERSION = 5`.
- **Save package:** its own format, `foundation/persistence/save_schema.py`, `CURRENT_RPG_SCHEMA_VERSION = 7`.
- **Newer documents:** `upcast_if_outdated` returns a document at or above the current version as stored, so older
  code silently misreads a newer document.
- **Sections are untyped mappings.** 132 `simulation_state` and 144 `runtime_state` keys are read by string†. Across
  the package there are 5,384 `dict[str, Any]`, 1,450 `deepcopy(` and 439 `except Exception`.
- **Replicated results.** The companion-acceptance path copies one result into `result`, `result.result`,
  `turn_contract` and `resolved_result` (`player_turn_execution.py:150-330`).
- **Two inventories.** Inventory lives in the character sheet and in the simulation (`player_state.inventory_state`),
  reconciled on save.
- **Where campaigns live.** 52 campaigns were on the operator database at envelope version 5 on 2026-10-14.
  Desktop v0.1.0 (2026-10-23) ships with an updater and has no guard against newer documents.
- **Tenancy.** RPG tables carry `workspace_id` and `owner_user_id`; row-level security is platform-wide (migration
  0106).

**Mechanics.**
- **Combat** runs on three paths:
  - `rules/combat/runtime*` (world-bestiary fights, blow by blow);
  - the session's older engine (`session/combat_action_runtime.py`, `special_combat_turns.py`, `item_combat*`):
    abilities, stabilize, revive, reposition and companion commands;
  - tactical attack, through `tactical_spatial_service`.
- **Defeat:** a lost fight sets HP to `max_hp // 10` and ends the fight (`runtime_attacks.py:319-323`).
- **Dice:** SHA-256 seeded (`rules/combat/rolls.py`).
- **Undo:** there is no undo or save-slot code outside the replay adapter.

**Published worlds at launch.** `genesis/worlds/published_world_setup.py` builds a per-session world model:
- places, exits and routes from canon;
- NPC homes guessed from text by word stems (`_npc_homes`);
- services from role keywords (`_role_services`);
- prices from canon text by keyword, with defaults (`_typical_price`);
- shop offers, including a built-in `healing_potion`.

**Evolving world.**
- **Pressure clock.** `world/causal_runtime.py` is a monotonic, hashed, replayable pressure clock, advanced per turn.
  It is bootstrapped from `campaign_bible.manifest.causal_runtime_bootstrap`, whose only writer is the campaign World
  Forge (`genesis/forge/world_forge_pipeline.py:76`). The published-world launch does not write it.
- **Two NPC routine systems:**
  - the NPC spatial runtime (migration 0027 tables, `/spatial-ticks`, its own clock);
  - in-state defaults: `DEFAULT_NPC_GOALS` covers `npc:Bran` and `npc:Mira`; `DEFAULT_NPC_SCHEDULES` covers
    `npc:Bran`, `npc:Mira`, `npc:Merchant` and `npc:GuardCaptain`.
- **Unseeded randomness:** `narration/narrative/event_injector.py`, `narration/cognitive/emotion_modifier.py:99`,
  `edge/agent/agent_scheduler.py:91,109`.
- **`uuid4` and wall-clock time:** `rules/quest/quest_models.py:27,117`, `rules/quest/quest_arc_engine.py:45`,
  `rules/choice/choice_models.py:39,93,98`, `world/memory/causal_memory.py:133`.
- **Reachability.** The static report finds 0 unreachable RPG modules, but it does not show which modules a turn
  executes.

**Narration safeguards that exist.**
- `narration/narrative_engine/` holds claim inference and support validation (`claims.py`), validation, a publisher
  guard, and authority checks.
- A narrative-response stream route exists, keyed by response id (`GET /api/rpg/narrative-responses/{id}/stream`).
  The web client does not use it.

**Starter content in code.**
- "Rusty Flagon"/`rusty_flagon` appears in 29 modules, including `rules/location_registry.py`, `world/locations/*`,
  `world/travel_graph.py`, `rules/party/companion_*`, `session/new_game.py` and `session/environment.py`.
- The demo preset is `demo_glimmerdeep_pass_lvl14`.
- `edge/dialogue_quality_benchmark.py` is built on Bran.

**Intent.**
- Two model advisories, `session/action_intelligence.py` and `session/semantic_action_intelligence.py`. They are
  skipped for commands the game resolves itself (bb83af47aa).
- About 83 word-list constants† across session, rules, world and narration.

**Performance.**
- **Overhead without model time.** `docs/measurements/rpg-turn-overhead-2026-10-15.json`, from
  `src/tests/rehearsal/rpg/turn_overhead.py` (30 turns, revision `31ff66f834`):
  - p95 296 ms at 100 KB of state and 352 ms at 1 MB, against a 150 ms budget;
  - 44 SQL statements per turn;
  - 3.4 model calls per turn.
- **Live**, with Claude Haiku through the Claude CLI (from commit notes): look 22 s, arrival 8 s, a question about
  3 s, a fight turn 9–14 s.

**Web.**
- **Polling.** The client polls the job (1,500 ms), the session (3,000 ms), the turn draft (`TURN_DRAFT_POLL_MS`)
  and the map (`RpgMapSurface.tsx:38`, 2,500 ms).
- **Hermes panels.** `RpgHermesSequenceJobPanel` always renders. `RpgHermesSequenceReviewPanel` and
  `RpgHermesExecutionHistory` return `null`, but their queries still run.
- **Campaign wizard.** `RpgCreateCampaignWizard` renders `RpgCreateCampaignWizardLegacy` for published-world
  launches.
- **Styles** use `@layer features`, with no `!important`.

**Tests and harnesses to build on.**
- **Turn golden:** `src/tests/characterization/test_rpg_production_turn.py`. It runs on PostgreSQL with a scripted
  model keyed by call contract, seed 7, and five starter-town commands.
- **Replay and endurance:** the 50-turn `FakeLLMProvider` replay and the 1,000-turn endurance check (WP-3.3a).
- **Integration tests:** `test_foreground_turn_transaction_integration.py`,
  `test_rpg_narrative_atomic_turn_integration.py`, `src/tests/unit/test_rpg_turn_foreground_job.py` and
  `src/tests/hermes/`.
- **Quality harnesses:** the `dialogue_quality_benchmark` targets, and the GUI-3 evaluation's Wilson reporting.
- **Scripts:** `scripts/architecture_metrics.py`, `reachability_report.py`, `check_rpg_file_lines.py` (1,200-line
  budget) and `rpg_interactive_live_smoke.py`.
- **Desktop:** the desktop real-model gate (`realmodels.spec.ts`).
- **Known noise:** eight session route tests fail instead of skipping when `OMNIX_DATABASE_URL` is unset.

## 4. Target architecture

### 4.1 One turn pipeline

Every state-changing request is a **turn** of one of these kinds:

| Kind | Covers |
|------|--------|
| `player_text` | the composer |
| `structured_action` | loadout, map actions, tactical move and attack, practice, quick actions, Hermes commands, rewind |
| `world_tick` | idle resume, ambient tick, spatial tick, continue |
| `system` | schema upcast, and nothing else |

Read-only routes stay as they are.

```
TurnRequest(kind, session_id, submission_id, based_on_revision, text | action | elapsed_time)
  0. accept      the submission takes its place in the campaign's submission queue (below)
  1. load        CampaignState (typed), once, at the latest committed revision;
                 fold in the proposals of turns whose narration is final, and record which (below)
  2. interpret   player_text only: text -> IntentCandidate[] (grammar first; one model call if needed)
  3. plan        -> PlannedAction, validated against the world model; for dialogue, a DialoguePlan (below);
                 may end the turn with a question
  4. resolve     PlannedAction -> StateChange[] (the owning mechanic's resolver; pure)
  5. apply       reducer(state, changes) -> state' (the only mutation; emits the JSON Patch)
  6. world tick  state' + in-game time elapsed -> StateChange[] (routines, pressures, events; seeded; reducer)
  7. commit      at the head of the queue, under a short campaign row lock: re-check the revision (re-run steps 3-6
                 against the new state if it moved), then one unit of work; emits `committed`, then `outcome`
  8. narrate     TurnOutcome (+ DialoguePlan) -> narration, streamed as `narration.delta`
  9. verify      narration vs TurnOutcome (narrative_engine claim checks); on failure, the fallback line
 10. finalize    insert the immutable narrative response(s); mark the delivery final (no campaign save, no revision)
 11. follow-ups  durable jobs: scene lore, images
```

**The submission queue.**
- **Order.** Each campaign has a FIFO of submissions. On acceptance, a submission row gets the next per-campaign
  sequence number, and turns commit in that order.
- **Locks.** Only step 7 takes a lock: the campaign row, for the unit of work alone. Its target is ≤ 100 ms, well
  inside the 5 s `lock_timeout`. Interpretation and planning, including any intent model call, run outside every
  lock, against the latest committed state.
- **Re-checking at commit.** At commit, if the revision moved since planning, steps 3–6 re-run against the new
  state. They are deterministic and make no model call; the intent candidates are reused. This is how a second tab's
  `player_text` turn "runs against the current state".
- **View-dependent actions.** A `structured_action` whose meaning depends on what the player saw (a grid cell, an
  item slot) carries `expected_revision`. If that is stale, it is refused with the fresh state instead of re-planned
  (RQ-8.9).
- **One token.** The campaign revision is the only concurrency token. The map's `map_state_revision` and the spatial
  `world_tick` become counters derived inside the campaign's commit.

**Where it runs.**
- **In the request:** steps 0–7, when no model call is needed before the commit and nothing is queued ahead of the
  submission. That covers structured actions, grammar-parsed commands and world ticks, so tactical moves answer at
  grid speed.
- **In a job:** otherwise, including when an earlier turn is still queued. The request waits up to 2 s for the turn
  to reach the head of the queue, then returns `accepted`, and the turn completes on the stream. A later fast
  submission never overtakes an earlier queued one.
- **Always in a job:** steps 8–10.
- **Idempotency:** either way, the `submission_id` is the idempotency key, under the same submission policy as today's
  turn jobs.

**The unit of work** extends `persist_foreground_turn`. In one transaction it writes:
- the campaign document and its new revision;
- the turn row, with `document_version`, the patch, the ids of the proposals it folded in, `state_hash_after` and
  `maps_hash_after`;
- a consumed marker for each folded-in proposal, unique per proposal id;
- the interaction, and the submission;
- canon changes and queued jobs;
- a delivery row in `omnix_rpg_narrative_deliveries`, with status `pending`;
- map-instance and map-event rows, when the turn moved anyone on a map.

**Maps get their own hash.**
- `state_hash_after` stays the document hash, so the existing chain is unchanged: the next turn's
  `state_hash_before` is this turn's `state_hash_after`, and snapshots verify the document hash they store.
- The RQ-1.1 migration adds `maps_hash_after` to turn rows: the hash of each map-instance snapshot the turn touched,
  in id order.
- Replay rebuilds those map instances from `omnix_rpg_campaign_map_events` and checks both hashes. W1's replay
  therefore covers grid movement as well as place presence.

**Narration is outside the campaign document.**
- **Committed with the turn:** only the `pending` delivery row.
- **Finalizing** (step 10) inserts the immutable canonical response(s) into `omnix_rpg_narrative_responses` and marks
  the delivery `final`. A forward migration changes that table's key to `(workspace_id, campaign_id, turn_id, kind)`,
  so a turn can carry its main narration plus ambient, companion and audit records.
- **Transport only:** `omnix_rpg_narration_events` keeps its role.
- **Reads:** the play screen, the journal and the narrator's continuity builder read narration from the response
  table. For a pending turn they read its `DialoguePlan` and outcome.
- **The move:** RQ-1.1 lists and moves every reader and writer of `runtime_state.narration_artifacts`.
- **The atomic test** (`test_rpg_narrative_atomic_turn_integration.py`) becomes: "the turn commits with a pending
  delivery; finalizing inserts the response without touching the campaign."

**Narration side effects are proposals, not turns.**
- **What they are.** What narration changes today through `_apply_dialogue_state_update_from_narration` (dialogue
  memory that depends on the wording, minor canon) becomes typed proposals stored with the narration response.
- **Folding them in.**
  - The proposal set is chosen **at commit**, inside the step-7 re-check: every unconsumed proposal of an earlier
    turn whose narration is final. Step 1 only reads them, so the plan sees them.
  - They pass through the reducer and the rules that accept or drop them, before the re-run of steps 3–6.
  - The unit of work writes a consumed marker per proposal, unique by proposal id, so two racing turns cannot both
    fold in the same proposal; the loser's commit re-check sees it consumed.
  - The turn row records the ids, and replay applies exactly the recorded set, so the outcome does not depend on job
    timing.
- **Nothing important waits.** What an NPC was *planned* to say is part of the committed `DialoguePlan`, so the next
  turn's plan knows it even while the narration is still streaming. Proposals carry only what the wording added.
- **No collisions.** There is no extra revision to collide with the player's next turn. Proposals from the last turn
  before the player quits fold into the next session's first turn.

**Dialogue: rules decide, the model phrases.**
- **The plan.** For a question or a conversation, step 3 builds a `DialoguePlan` from the NPC's knowledge state,
  offers, quest hooks, prices and relationship. It sets what the NPC may reveal or offer this turn, and their stance.
- **Before the commit.** What the plan makes real becomes changes before the commit: `OfferPresented`,
  `QuestOffered`, `ClueRevealed`, `KnowledgeShared`, `RelationshipChanged`.
- **The line.** The narrator writes the NPC's line from the plan, and verification checks it against the plan and
  the outcome.
- **Fallback.** The fallback line is built from the plan with the NPC's authored voice lines, for example: "Brindle
  taps the price board: three silver for a healing potion." If the plan has nothing to say, it is a neutral beat
  ("Brindle shrugs.").
- **Speed.** A question to someone present stays fast: the grammar, plan and commit take milliseconds, and the line
  streams.

**Invariants**, each enforced by a test or a lint rule:
- **One mutation point.** Only the reducer changes campaign state.
- **One save.** Only the commit step persists campaign state. The listed exemptions are the persistence modules,
  campaign creation, import, adoption and admin routes.
- **One result.** `TurnOutcome` is a frozen model: kind, intent, planned action, applied changes, world events,
  dialogue plan, narration reference, presentation hints and timings. It is serialized once.
- **Narration has no authority.** Narration changes no state directly; its proposals pass through rules on the next
  turn.
- **Deterministic.** The purpose-scoped session RNG, seed-derived ids (UUID5) and the injected clock. The same inputs,
  model answers and recorded proposal sets give the same state hash.
- **Early answers are still turns.** Fast dialogue, clarification and refusals produce a `TurnOutcome` and commit,
  possibly with no changes.

### 4.2 Typed campaign document v6

The campaign document goes from envelope version 5 to **6**. The save package goes from 7 to **8**, which carries a
v6 document. The envelope version governs state layout and replay; the package version governs only the export file.

Sections become pydantic models in `foundation/state/`:

| Section | Holds |
|---------|-------|
| `player` | sheet, stats, HP, skills, equipment |
| `inventory` | one store: stacks, purse, ground items by location |
| `location` | where the player is, discovered places and routes |
| `time` | tick, in-game clock, calendar |
| `party` | companions |
| `combat` | the current fight |
| `quests` | quest progress |
| `survival` | needs |
| `npcs` | runtime only: place and cell, current routine step and goal cursor, relationships, what each NPC has shared, memory references. Authored routines, goals and knowledge stay in the world revision, referenced, not copied. |
| `world` | pressures, factions, events, rumors |
| `economy` | stock, prices, outstanding offers |
| `narrative` | journal pointers and recent beats; narration text lives in the narration tables |
| `meta` | seed, turn index |

Each model has `extensions: dict[str, Any]` for keys not yet typed, so the move lands section by section. A typed view
(`CampaignStateView`) lets untyped code read a v6 document during the transition.

**Storage support.** RQ-1.1 adds a forward migration in `src/app/apps/rpg/migrations`:
- a `document_version` integer on turn rows and snapshots;
- a `pinned` flag on snapshots, which retention never deletes.

**The upcast is its own revision.** At revision R the stored v5 document is pinned as the pre-upgrade backup. The
upcast is a `system` turn at R+1: a turn row with `document_version = 6`, no player input, and a pinned v6 snapshot.
The upcaster:
- merges the two inventories, with the simulation store winning where they disagree;
- moves known keys into their sections and keeps the rest in `extensions`;
- moves narration artifacts into the narration tables;
- binds campaigns with no world reference to the starter or demo bundle (RQ-2.8).

**Replay.**
- Patches replay in their own `document_version`, and hashes are compared only within a version.
- A chain is verified from the nearest snapshot at or before its start.
- Where today's out-of-turn saves left revisions without patches (counted per campaign in RQ-0.9), verification
  restarts at the next snapshot.
- After RQ-1.4 no revision lacks a patch.

**Newer documents are refused.** A document whose `document_version` is newer than the code is refused with a clear
error, instead of being read as stored.

### 4.3 One owner per mechanic

| Mechanic | Owner (resolver) | Absorbs | Deletes or retires |
|----------|------------------|---------|--------------------|
| Combat | `rules/combat/runtime` | abilities, conditions, stabilize, revive, reposition, companion commands, flee, tactical move and attack | `session/combat_action_runtime.py`, `special_combat_turns.py`, `combat_action_reconciliation.py`, `combat_result_reconciliation.py`, the `fast_combat_*` hooks and the `item_combat*` duplicates; `tactical_spatial_service` becomes a `structured_action` producer |
| Inventory and purse | `rules/interactions/inventory` | use, equip (including loadout), drop, pick up, craft, salvage, give | the sheet-side inventory and the `item_*_session` adapters that write both stores |
| Trade and services | `rules/economy/service_resolver` | buy, sell, lodging, meals, repairs, paid information | the starter merchant fallback and stub-rumor canonicalization in `service_living_world` |
| Quests | `rules/quest` | accept, progress, complete, fail, rewards, quest offers | quest progress in `combat_quest_*` and `published_opening_progress` |
| Survival and rest | `rules/economy/survival` + `rules/interactions/survival_action_runtime` | needs tick, rest, eating | the early-return copies of `apply_survival_runtime_tick` |
| Party | `rules/party` | join, leave, commands, loyalty | the copies in `companion_turn_enrichment` |
| Travel and maps | `world/locations/travel` + `world/map_actions` | routes, travel time, arrival, map actions | the starter-town fallbacks in `travel_graph` and `location_registry` |
| NPC routines | `world/npc_spatial_*`, ported to the `npcs` section's cursors | schedules, goals, transitions | the spatial runtime's mutable state tables and clock (retired by migration; history tables stay, bounded) and `DEFAULT_NPC_GOALS` / `DEFAULT_NPC_SCHEDULES` (moved into the starter bundle) |
| Dialogue | `narration/runtime/dialogue_runtime` + `rules/dialogue/plan` | questions, conversations, what an NPC reveals and offers | the duplicate fast and slow dialogue writers |
| Skills and progression | `rules/player` | practice, XP, level-up | the XP projection in `combat_xp_projection` |

A registry test lists each owner and fails when a second module writes the same state section (`src/tests/unit/rpg/test_mechanic_owners.py`, RQ-2.9).

### 4.4 Every campaign plays from a world

The starter town (the Rusty Flagon, its cast and roads) and the Glimmerdeep demo become bundled worlds under
`resources/examples/rpg/world-bundles/`, installed like Aurelia. New-game and demo campaigns launch from them, and
engine code holds no world content.

The world schema gains explicit sections, authored or generated, and validated at release:

- **Economy:** shops, what each provider sells and buys back, prices, stock and restock.
- **Routines:** each named NPC's schedule (place by time of day) and goals.
- **Knowledge:** what each NPC knows and will share, and on what terms; it feeds the `DialoguePlan`.
- **Pressures:** the pressure plan the causal runtime needs.
- **Bestiary and loot:** creatures, behaviours, drops.

The bundle format gets a new version, and older bundles still import. For worlds published before these sections
existed, launch derives them with today's inference (`published_world_setup.py`), and launch readiness reports
"derived, not authored".

### 4.5 Living world

The world tick (step 6) runs with the in-game time the turn took. There is one in-game clock, the `time` section.

The spatial runtime's routine, goal and transition logic is ported to run on the `npcs` section's runtime cursors,
reading authored routines and goals from the world revision. Its mutable state (`_goals`, `_routines` runtime
fields, the clock) moves into the document. Its history (`_transitions`, `_tick_runs`, decisions) stays in its tables,
bounded by a retention policy, and is written in the turn's unit of work. `/spatial-ticks` becomes a `world_tick`
turn. Cell positions stay in the map-instance snapshots, which `maps_hash_after` covers.

- **Routines** move NPCs between places by time of day, and who is present follows.
- **Goals** bias the `DialoguePlan` and offers, and can create events. For example, a smith short of ore raises
  prices and posts a job.
- **Pressures** advance on the causal clock, and player changes feed them: clearing creatures lowers a threat, and
  buying out stock raises scarcity.
- **Events** reach the player as a notice, a rumor at the inn, a line from someone present, or a journal "World"
  entry. A budget per in-game hour limits them, favouring the player's places, quests and companions.
- **Time away** is one `world_tick` turn that runs the tick at region resolution for the elapsed in-game time,
  capped at 24 in-game hours per catch-up. The resume recap lists only changes that happened.

### 4.6 Understanding the player

A command grammar (`rules/intent/grammar.py`) parses unambiguous commands against the world model's entities:
people present, items carried, exits and offers. Examples: "buy the healing potion", "go to Skybridge Pass", "attack
the echo wolf with my dagger".

When the grammar is not confident, one structured model call returns ranked `IntentCandidate` values, which the
planner validates. When two readings remain, the turn asks one question. The word lists are deleted or folded into
the grammar's lexicon, which matches whole words only.

If the provider is down or slow (RQ-8.8):
- only grammar-parsed commands run;
- narration uses the fallback line;
- the play screen says the storyteller is unavailable.

### 4.7 Transport and presentation

The web client subscribes to `GET /api/rpg/sessions/{session_id}/submissions/{submission_id}/stream` (SSE). It is
scoped to the submitting user, like the turn draft, and shares its implementation with the narrative-response stream.

| Event | Sent when |
|-------|-----------|
| `accepted` | the turn is received |
| `committed` | the unit of work has committed |
| `outcome` | after `committed`; the outcome card renders at once |
| `narration.delta` | each streamed chunk of narration |
| `narration.final` | the narrative response is inserted and the delivery is final |
| `error` | the turn failed |

Reconnecting with the submission id resumes the stream, and polling stays as the fallback. The response-id stream
route is kept for its existing consumers or retired in RQ-6.2. The map surface receives map changes from the same
stream instead of polling every 2.5 s.

## 5. Phases and work packages

**Sizes** are upper bounds of focused work: S ≤ 3 days, M ≤ 2 weeks, L ≤ 4 weeks.

**Effort.** At upper bounds the packages sum to about 110 weeks. The assumption is one owner directing AI coding
sessions in two lanes:
- **Lane A:** the turn core and mechanics. RQ-0.2/0.3, then RQ-1 → RQ-2 → RQ-5 → RQ-9, about 60 weeks.
- **Lane B:** harnesses, intent and narration, performance, play screen, living world, trust. RQ-0 (the rest) →
  RQ-3 → RQ-6 → RQ-7 → RQ-4 → RQ-8, about 54 weeks including waits for lane A.

Lane A is the critical path: about 60 weeks, roughly 14 months at upper bounds. At the roughly 60% of upper bound
that recent packages have taken, that is about 9 months.

Each package closes with its tests, the gate set for its phase (§6), and a row in `docs/roadmap/PROGRESS.md`.

**Dependencies:**
- RQ-1 waits for RQ-0.2, RQ-0.3 and RQ-0.9. RQ-1.7 ships in a release before RQ-1.1 writes any v6 document.
- RQ-2 waits for RQ-1.4. Within RQ-2, RQ-2.0 and RQ-2.7 come first.
- RQ-3 waits for RQ-1.3.
- RQ-6 waits for RQ-1.4.
- RQ-7 waits for RQ-1.3.
- RQ-4 waits for RQ-2.0, RQ-2.3 and RQ-2.7.
- RQ-5 waits for the RQ-2 mechanics it extends. RQ-5.2 also waits for RQ-3.1, and RQ-5.4 (pressure-driven side
  quests) for RQ-4.2. Lane A therefore does RQ-5.4 last within RQ-5.
- **Release cadence is on the critical path.** RQ-1.1 cannot write v6 until a release carrying RQ-1.7 has reached
  the operator and the desktop update channel. Plan that release at the start of RQ-1.
- RQ-8 may start after RQ-0, except that RQ-8.3's stream tests wait for RQ-6.2, and RQ-8.5 and RQ-8.9 wait for
  RQ-1.4.

```
lane A: RQ-0.2/0.3 ─> RQ-1 ─> RQ-2 (2.0, 2.7 first) ─────────────> RQ-5 ─────────> RQ-9
                         │           │                                              ^
lane B: RQ-0 rest ───────┴─> RQ-3 ─> RQ-6 ─> RQ-7 ─> RQ-4 (after 2.0, 2.3, 2.7) ─> RQ-8
```

### Phase RQ-0: Baseline and safety net

No behaviour changes. Every later phase is measured against this.

- **RQ-0.1 Scorecard script (S).** `scripts/rpg_scorecard.py` computes the static metrics in §2, with its patterns
  stated in the script:
  - string-key state reads in the turn path;
  - save call sites;
  - `dict[str, Any]`, `deepcopy` and `except Exception`;
  - world-specific names;
  - word lists, `random`, `uuid4` and clock reads;
  - cross-context imports outside `contracts`;
  - file sizes.
  
  It writes `docs/measurements/rpg-scorecard-<date>.json`. The shrink-only metrics become ratchets in
  `architecture_metrics.py`, and the † baselines are replaced.
- **RQ-0.2 Published-world golden (M).** Launch Aurelia from its bundle and play 30 scripted turns:
  - covered: look, talk, ask about a price, buy, sell, drop, pick up, travel, fight, a tactical move, quest accept and
    progress, rest, wait;
  - recorded per turn: applied changes, the session summary and the state hash;
  - prose goes in a separate snapshot that may be re-recorded;
  - the scripted model answers by semantic role (intent, narration, dialogue line, lore) through one adapter, not by
    prompt contract.
- **RQ-0.3 Playthrough suite (M).** Deterministic scenarios with the role-keyed model, asserting state after each
  turn, on Aurelia, Vesper-9 and the starter town:
  - a trade round trip (purse exact);
  - an inventory round trip (drop, leave, return, pick up, stack);
  - fights to victory and to defeat, and fleeing;
  - a tactical move and attack;
  - equipping through loadout;
  - a companion joining, taking a command, and leaving;
  - a quest from offer to reward, including an NPC offering it in conversation;
  - lodging and needs over a night;
  - travel across three places and back;
  - skill practice up to a level;
  - a refused action;
  - a question to someone present;
  - an ambiguous command;
  - idle resume;
  - two tabs submitting at once, including both turns loading while an earlier turn's narration proposal becomes
    final (the proposal is folded in exactly once).
  
  Each bug fixed since 2026-10-20 becomes a scenario.
- **RQ-0.4 Intent corpus (L).** 2,000 labelled player inputs across the three worlds:
  - **split:** an 800-item development set, and a 1,200-item held-out set that is frozen and used only for gates;
  - **held-out mix:** at least 800 not stateful, and at least 700 with a target entity;
  - **labels:** action family, target entity (where there is one), and stateful or not;
  - **contents:** the known traps ("useful", "forest", "white", "current"), typos, multi-step commands and questions;
  - **labelling:** model-assisted, with every label reviewed by a human;
  - **report:** a harness gives each metric with its own denominator and Wilson bounds. Baseline recorded.
- **RQ-0.5 Latency harness (S).** Runs each turn class 20 times per provider: look, arrive, question, buy, fight,
  tactical move, status and wait. It records:
  - outcome visible, first narration visible, and complete turn;
  - model calls;
  - overhead.
  
  It writes `docs/measurements/rpg-latency-<date>.json`. The overhead rehearsal moves to 200 turns per state size,
  and gains a world-tick case: a 24-in-game-hour catch-up.
- **RQ-0.6 Narration eval (M).** 900 narrated turns, 300 per world, at least 600 with a speaker:
  - **deterministic checks:** narration claims against applied changes and the `DialoguePlan` (using
    `narrative_engine/claims.py`), speaker identity, and private canon not leaked;
  - **model-judged rubric:** grounded, continuous, varied. The judge is calibrated on 150 human-labelled items and
    gates only with agreement ≥ 0.90 and Cohen's κ ≥ 0.70;
  - **near-duplicate:** a narration whose word 5-gram Jaccard similarity with any of the previous 10 narrations in the
    same campaign is ≥ 0.6.
  
  The report gives each metric's n and Wilson bounds. Baseline recorded.
- **RQ-0.7 Test hygiene and turn path (S).** The eight session route tests skip without a database URL. Coverage over
  the playthrough suite records the turn path (`[rpg_turn_path]`) and the modules no scenario executes (input to
  RQ-2.10).
- **RQ-0.8 Entry-point inventory (S).** Every mutating RPG route and job, with what it writes and its concurrency.
  Each gets a turn kind (§4.1) or a listed exemption with a reason.
- **RQ-0.9 Replay and size audit (S).** For every operator campaign, dumped to the scratch database:
  - count the revisions without patches;
  - count the chains that do not replay to their stored hashes;
  - measure the document size per section, and project the v6 `npcs` section's size for the largest world (Aurelia),
    to check F2's 1 MB budget before RQ-1.1.
  
  Record the results.

**Exit:** the scorecard, latency, intent, narration and replay baselines are committed under `docs/measurements/`.
The golden and the suite pass on current code; any defects they find are fixed, or recorded as `xfail` scenarios.

### Phase RQ-1: Typed turn core

- **RQ-1.1 Campaign document v6 (L).** The section models, `CampaignStateView`, and the v5 → v6 upcaster as a
  `system` turn. It also adds the `document_version` and `pinned` migration, package format 8, and the narration move
  into the narration tables. That move includes the `(…, turn_id, kind)` key migration and every reader and writer of
  `narration_artifacts` (§3). Every operator campaign on the scratch database must:
  - verify its v5 chains as RQ-0.9 recorded;
  - upcast with a pinned backup and a pinned v6 snapshot;
  - validate;
  - take one v6 turn.
  
  The owner reviews the inventory-merge diffs (§7 Q-2).
- **RQ-1.2 StateChange and reducer (M).** A closed vocabulary of change types, a reducer, and the JSON Patch built
  from the changes. A property test checks that applying the changes, and applying the patch, give the same document.
- **RQ-1.3 TurnOutcome (M).** The turn result model, the route serialization, and the generated web contract and
  client. A single adapter feeds the old payload to Hermes and replay until RQ-1.6.
- **RQ-1.4 Pipeline skeleton (L).** `session/turn/` implements §4.1:
  - the turn kinds;
  - the submission queue and its commit-time re-check;
  - in-request and job execution;
  - the extended unit of work, with pending deliveries, `maps_hash_after` and proposal consumed markers;
  - narration finalization and proposals;
  - the SSE events, backend only.
  
  Look and wait move behind it first, as the proving mechanic. Each mechanic then moves in RQ-2, behind a per-mechanic
  setting (`OMNIX_RPG_TURN_PIPELINE_<MECHANIC>`, for development and the operator only). The setting defaults on once
  its scenarios pass, and is removed one release later.
- **RQ-1.5 Lint (S).** Rules over `[rpg_turn_path]`: state mutation only in the reducer; campaign saves only in the
  commit step and the listed exemptions; no string-key reads of state sections. Baselines start at today's counts and
  reach 0 by the end of RQ-2.
- **RQ-1.6 Hermes and replay on TurnOutcome (M).** The Hermes RPG feature (`edge/hermes`, 44 modules) submits turns
  keyed by `submission_id` and reads `TurnOutcome`; so does the replay adapter. Where Hermes needs blocking narration
  (`narration_mode: "blocking"` today), it waits for `narration.final`, with a timeout that falls back to the
  deterministic line. The RQ-1.3 adapter is deleted, and
  `src/tests/hermes/` stays green.
- **RQ-1.7 Upgrade safety (S, ships first).**
  - Refuse newer documents.
  - Pin the pre-upgrade snapshot.
  - Exempt pinned snapshots from retention.
  - Add a desktop upgrade test: an install with v5 campaigns updates and plays them.
  
  This ships in an operator and desktop release before RQ-1.1 writes any v6 document.

**Exit:** look and wait run on the pipeline; golden and suite green; F2 no worse than baseline.

### Phase RQ-2: Mechanics onto the pipeline, one engine each

Each package moves a mechanic behind the pipeline and consolidates it to its single owner (§4.3) at the same time.
Its scenarios must stay green.

- **RQ-2.0 World schema sections, core (M).** Economy, routines, knowledge, pressures, bestiary and loot (§4.4), in
  the world model and the bundle format, with validation and the inference fallback.
- **RQ-2.1 Travel and maps (M).** Travel, arrival and map actions.
- **RQ-2.2 Dialogue (M).** `DialoguePlan`, dialogue change types, narration proposals and the fallback line; the
  duplicate writers deleted.
- **RQ-2.3 Trade and services (M).** Offers and sell-back rules from the economy section only, with no global
  fallback provider.
- **RQ-2.4 Inventory, loadout and survival (L).** One store; world item catalogs; stacking; ground items; loadout
  actions; survival needs and rest.
- **RQ-2.5 Quests and party (M).** Quest state and offers; companions.
- **RQ-2.6 Combat and tactical (L).** One engine, tactical commands included. The older session engine is deleted,
  and `tactical_spatial_service` uses the campaign revision as its only token.
- **RQ-2.7 World ticks (M).** Idle resume, ambient ticks, `/spatial-ticks` and continue become `world_tick` turns. The
  spatial runtime is ported to the `npcs` section; its state tables are retired by a forward migration after a release.
  This is the only package that moves ticks; RQ-4 builds behaviour on it.
- **RQ-2.8 Starter town and demo as bundles (M).**
  - Extract the Rusty Flagon content (with its NPC goals and schedules) and the Glimmerdeep demo into world bundles
    with RQ-2.0 sections.
  - The upcaster binds old campaigns to them.
  - Delete the literals, and add the A4 lint.
  - Move the `dialogue_quality_benchmark` fixtures to test fixtures.
- **RQ-2.9 Registry test (S).** The owner table in §4.3, as a test.
- **RQ-2.10 Dead and duplicate code (M).** Review the modules no scenario executes (RQ-0.7) with the owner, and delete
  them with their tests, as in R-3.

**Exit:**
- A2, A3 and A4 at target;
- RQ-1.5 lint baselines at 0;
- the old turn chain deleted: the `_TURN_APPLY_STAGES` chain, the nested `apply_turn` layers, the PART39/PART40
  wrappers, and the early-return saves.

### Phase RQ-3: Intent and narration

- **RQ-3.1 Command grammar (M).** §4.6.
- **RQ-3.2 One intent call (M).** Ranked candidates, planner validation and clarification. The word lists are deleted.
- **RQ-3.3 Narration contract (M).** The narrator's input is `TurnOutcome` plus the `DialoguePlan` and scene canon.
  Verification extends `narrative_engine/claims.py`, `validation.py` and `publisher_guard.py`. Each turn makes one
  narration call.
- **RQ-3.4 Untrusted world text (S).** Bundle canon is delimited as data in prompts, and RQ-8.1 tests it.

**Exit:** M2 on the held-out set and N1 at target.

### Phase RQ-4: Living world

- **RQ-4.1 Authoring and generation (M).** The authoring UI for the RQ-2.0 sections, World Forge generation of them,
  and launch readiness ("authored" or "derived").
- **RQ-4.2 Pressure clock everywhere (M).** Published-world launches bootstrap the causal runtime from the pressure
  plan, and the clock advances by in-game time.
- **RQ-4.3 Routines and goals (M).** Routines run for every named NPC, and who is present follows. Goals bias the
  `DialoguePlan` and offers.
- **RQ-4.4 Consequences and surfacing (M).** Player actions emit pressure changes, and events reach the player within
  the surfacing budget.
- **RQ-4.5 Time away (M).** A capped region-resolution catch-up inside the idle `world_tick` turn, and the recap of
  real changes.
- **RQ-4.6 Determinism (S).** Seed `event_injector`, `emotion_modifier` and `agent_scheduler`, or delete them if
  RQ-2.10 shows no turn runs them. Use seed-derived ids and the injected clock for quests, choices and causal memory.
  Widen AL013 to `[rpg_turn_path]`.

**Exit:** W1 and D1 at target.

### Phase RQ-5: Gameplay depth

Each item starts with a one-page design note in `docs/rpg/design/`, approved by the owner, then a resolver and
scenarios.

- **RQ-5.0 Design pack and rubric (S).** The note template, balance bands, and the playtest rubric: stakes, choice,
  progression, living world, clarity and speed, each 1–5 with anchors.
- **RQ-5.1 Stakes (M).** The defeat model (§7 Q-1), persistent injuries and conditions, and fleeing with a cost.
- **RQ-5.2 Checks (M).** d20 + skill against a difficulty for persuade, sneak, climb, pick a lock and recall lore,
  shown to the player. Failure moves the story on.
- **RQ-5.3 Progression (M).** An XP curve and level-up choices, with skills tied to the world. A 500-turn balance
  simulation stays inside the bands.
- **RQ-5.4 Quests (M).** Multi-step quests with branches and failure, quest givers from the world, and side quests
  from active pressures, with seeded ids.
- **RQ-5.5 Economy balance (S, stretch).** Sinks and sources, and prices that move with scarcity.
- **RQ-5.6 Encounters (M, stretch).** Creature behaviours from the bestiary, with negotiation and stealth as
  alternatives to fighting.
- **RQ-5.7 Rewind and save points (S).** Undo the last turn and named save points. A rewind is a `structured_action`
  that restores an earlier revision's document as a new revision.

**Exit:** G1 at target, including the owner playtest.

### Phase RQ-6: Performance

- **RQ-6.1 Call budget (M).** F3, asserted by the latency harness.
- **RQ-6.2 SSE turn stream (M).** The §4.7 route and client, replacing the job, session, draft and map polls. Decide
  whether to keep the response-id stream.
- **RQ-6.3 Outcome first (S).** With RQ-7.2.
- **RQ-6.4 Overhead (M).** One load and one unit of work per turn; typed state removes most deep copies; bounded
  histories; the world-tick budget.
- **RQ-6.5 Prompt budgets and caching (S).** A stable world-canon prefix for providers with prompt caching.

**Exit:** F1, F2 and F3 at target with the reference model.

### Phase RQ-7: Play screen

- **RQ-7.1 Player-first layout (M).** Story and composer at the centre, with rails for the rest. Developer panels sit
  behind Developer mode, the stubbed Hermes panels and their queries are removed, and the wording is for players.
- **RQ-7.2 Outcome card (S).** Shows coin, items, HP, conditions, quest steps, offers and dice.
- **RQ-7.3 Suggestions and clarification (S).** Suggestions as chips, and clarifications as choices.
- **RQ-7.4 One creation flow (M).** World → opening → character → play. `RpgCreateCampaignWizardLegacy` is deleted.
- **RQ-7.5 Structure (L).**
  - Split `rpgUiState.ts`, `RpgLoadoutTabs.tsx`, `RpgWorkspace.tsx` and `RpgActionComposer.tsx`, so no file is over
    600 lines.
  - One stylesheet per component.
  - Playwright screenshots in light and dark at 360, 768 and 1,440 px.
- **RQ-7.6 Accessibility (S).** A live region for narration, keyboard play, axe with 0 serious or critical issues,
  and reduced motion.
- **RQ-7.7 Core tasks (S).** A Playwright suite at 360 × 740 and 1,440 × 900, also used for the owner session. Tasks:
  start a campaign in a bundled world, buy and sell, equip, travel, fight on the grid, take and finish a quest, rest,
  undo a turn, and resume after time away.

**Exit:** U1 and U2 at target; the owner usability session is done.

### Phase RQ-8: Trust and operations

- **RQ-8.1 Injection corpus (S).** World bundles that try to instruct the model change no state, leak no private
  canon, and gain no authority.
- **RQ-8.2 Model budget (S).** Per-user limits on model calls from RPG routes.
- **RQ-8.3 Tenant isolation (S).** Campaigns, drafts, narrative responses and deliveries, and the submission stream are isolated
  between users.
- **RQ-8.4 Operations view (M).** Turn failure rate, degraded-stage rate, latency per turn class and model cost per
  turn, per day.
- **RQ-8.5 Crash mid-turn (S).** Killing the gateway at each pipeline step leaves either the committed turn or none.
  A pending delivery is finished by the retried job, idempotently by `submission_id`.
- **RQ-8.6 Campaign export and import (S, stretch).** In package format 8, with the campaign's narrative responses.
- **RQ-8.7 Bundle assets (S).** SVGs sanitized or rasterized at import, a restrictive CSP on asset routes, and a
  review of the size and entry limits.
- **RQ-8.8 Provider outage (S).** Timeouts per call kind, grammar-only intent, the fallback line and a notice. Tested
  with a failing fake provider.
- **RQ-8.9 Stale view-dependent actions (S).** A stale `structured_action` is refused with the current state and a
  plain message. `player_text` turns from a second tab run against the current state. Both are in the suite.
- **RQ-8.10 Retention and privacy (S).** A long campaign is compacted: turns older than the configured horizon fold
  into a pinned snapshot, then their rows, player text and narration are deleted. Replay starts at that snapshot.
  Deleting a campaign deletes everything. The policy is documented in `docs/OPERATIONS.md`.

**Exit:** S1, O1 and P1 at target.

### Phase RQ-9: Production gate

- **RQ-9.1 Autoplay (M).** A model-driven player plays three worlds for 500 turns each, against the reference model.
  A state auditor checks every turn against the change log, and every defect is fixed with a scenario.
- **RQ-9.2 Owner playtest (S).** Two hours in two worlds, scored on the RQ-5.0 rubric. Every P0/P1 is fixed.
- **RQ-9.3 Documentation (S).** A player guide, a world-author guide (the new schema sections) and operator notes.
- **RQ-9.4 Final scorecard (S).** Every area at Strong or better, recorded in `docs/measurements/`.

## 6. Gate set

Gates run locally before a phase closes; CI is not watched for roadmap work. PostgreSQL tests use the scratch test
database with `OMNIX_TEST_DATABASE_URL` set literally, never the live database. Model-dependent gates (†) run at the
RQ-0 baseline, at the exits of RQ-3, RQ-6 and RQ-9, and when a change touches prompts or intent. Other phases run them
only on request (§7 Q-6).

| Gate | Command or harness | Pass |
|------|--------------------|------|
| Python RPG suites | `.venv/dev-clean/Scripts/python.exe -m pytest src/tests/rpg src/tests/unit/rpg src/tests/unit/test_rpg_turn_foreground_job.py src/tests/characterization src/tests/hermes -n 0` | 0 failures |
| Persistence | `pytest src/tests/persistence/test_foreground_turn_transaction_integration.py src/tests/persistence/test_rpg_narrative_atomic_turn_integration.py`, plus the campaign-state upcaster and retention tests | 0 failures |
| Published-world golden | RQ-0.2 | Matches, or the diff is explained in the commit |
| Playthrough suite | RQ-0.3 | 100% |
| Web RPG tests and build | `npm --prefix web run test -- src/features/rpg`; `npm --prefix web run build` | Pass |
| Architecture | `scripts/architecture_metrics.py` (AL013, AL017, the RQ-1.5 rules, the A1 ratchet); `scripts/check_rpg_file_lines.py` | No ratchet regresses |
| Scorecard | `scripts/rpg_scorecard.py` | The phase's targets |
| Intent corpus † | RQ-0.4, held-out set | M2 (from RQ-3) |
| Narration eval † | RQ-0.6 | N1 (from RQ-3) |
| Latency † | RQ-0.5, reference model | F1 and F3 (from RQ-6) |
| Overhead | `src/tests/rehearsal/rpg/turn_overhead.py`, 200 turns per size, plus the world-tick case | F2 |
| Replay | The 1,000-turn replay and the upcast-boundary replay | Identical hashes within each version |
| Accessibility and core tasks | RQ-7.6 and RQ-7.7 Playwright suites | 0 serious or critical issues; all tasks pass |
| Desktop | `desktop/staging/stage.py app` after `git add`, then the desktop real-model gate playing one turn in a bundled world, and the RQ-1.7 upgrade test | Pass |

Model-dependent gates report Wilson bounds, each metric's n, and the provider's resolved model name.

## 7. Owner decisions

Answered by the owner on 2026-10-23: every proposed answer is accepted, with the changes noted in the last column.

| ID | Question | Decision | Owner note |
|----|----------|----------|------------|
| Q-1 | What does losing a fight mean? | A setback by default: the hero wakes at the last place they rested, hurt, with some coin or an item lost, and time has passed. A per-campaign "hardcore" option makes defeat final. | Accepted. |
| Q-2 | May the v5 → v6 upcast change campaigns where the two inventories disagree? | Yes. The simulation store wins, and the diff list is reviewed before the switch. | Accepted. |
| Q-3 | Do the starter town and demo stay, as bundled worlds? | Yes. | Accepted. |
| Q-4 | May the Hermes RPG panels move behind Developer mode? | Yes. | Accepted. |
| Q-5 | Which model is the latency reference? | Claude Haiku through the Anthropic API for the gate, with the Claude CLI reported alongside. | Accepted. |
| Q-6 | What model spend is acceptable for gates? | Per full run of the model-dependent gates: about 2,000 calls (900 narrations plus 900 judgments, intent calls for the 1,200 held-out inputs the grammar does not parse, and 320 latency turns). Run four times (RQ-0, RQ-3, RQ-6, RQ-9). RQ-9.1 autoplay adds about 3,000 calls once. | Accepted, and a higher budget is approved: spend what proper testing needs. |
| Q-7 | Do community worlds need a content rating before production? | A rating field, shown before adoption; no moderation service. | Accepted. |
| Q-8 | Is the two-lane staffing assumption (§5) right? | Yes. | Two lanes, run as two agents. |
| Q-9 | What retention horizon should RQ-8.10 compaction use? | Compact only campaigns over 5,000 revisions: their turns older than the newest 1,000 fold into a pinned snapshot. Smaller campaigns keep every turn. | Accepted. |

## 8. Risks

- **The pipeline move stalls with two turn paths.** Mechanics move one package at a time behind per-mechanic settings,
  with their scenarios green. The old chain is deleted at RQ-2's exit, not sooner.
- **Golden churn hides regressions.** The golden and the suite assert state, with the model keyed by semantic role.
  Prose snapshots are kept separately.
- **The upcast damages saves.** `extensions` keeps unknown keys. The upcaster runs over every operator campaign first.
  A pinned pre-upgrade snapshot is kept, and newer documents are refused (RQ-1.7 ships first).
- **Desktop users upgrade mid-roadmap.** A desktop build only switches a mechanic to the new pipeline once its
  scenarios pass, and the desktop gate includes the upgrade test. Desktop users cannot switch mechanics back; the
  operator can.
- **Dialogue feels scripted when rules decide what an NPC offers.** The `DialoguePlan` decides only facts and offers.
  Voice, manner and small talk stay with the model, and the narration eval and owner playtest watch for stiffness.
- **The grammar plus one model call is less flexible than today's advisories.** The held-out corpus measures it,
  clarification covers ties, and the model call handles whatever the grammar does not parse.
- **Living-world events become noise.** A budget limits them, favouring the player's places, quests and companions.
- **Latency depends on the provider.** The gate names its reference model, and the outcome card comes first whatever
  the provider.
- **Scope.** About 110 weeks of upper-bound effort, with a critical path of about 60 weeks (§5). A shorter path can
  defer RQ-5.5, RQ-5.6, RQ-8.6 and every stretch target without leaving any area below Strong.

## 9. Out of scope

- Multiplayer or shared campaigns.
- Voice play and generated music. The speech services exist, but wiring them to the RPG is a separate plan.
- Mobile apps. The play screen must still work at 360 px in a browser.
- World Forge generation quality, beyond producing the new schema sections.
- The trading, agent runtime and memory subsystems.
- Internationalization. The RPG is English-only, like the rest of Omnix.

## 10. Review log

**Revision 1 (2026-10-23):** written from the 2026-10-23 evaluation of `rpg-evolve` at `ce84e4787e`.

**Revision 1 → 2 (2026-10-23), from an independent review against the code.** The review spot-checked 20 facts and
confirmed most of them; I re-checked the structural ones myself before revising.
- **Turn order:** the commit now comes before narration.
- **Sequencing:** the world-schema core moved into RQ-2.
- **Versions:** the campaign document is v5 → v6 and the save package is 7 → 8, named separately.
- **Entry points:** tactical, loadout, map actions, spatial ticks, continue, Hermes and idle are listed and become
  turn kinds; NPC routines build on the spatial runtime.
- **Unit of work:** the commit extends `persist_foreground_turn`; verification builds on `claims.py`; the SSE stream
  builds on the existing stream.
- **Targets:** Wilson-based targets with stated n; measurability fixes for A1, the turn path, F1–F3, O1, U1 and G1;
  D1 widened to `uuid4` and clocks.
- **Upgrades and gates:** RQ-1.7 upgrade safety; missing gates added.
- **Effort and gaps:** re-estimated; RQ-8.7–8.10 added.
- **Corrections:** several facts fixed.

**Revision 2 → 3 (2026-10-23), second review pass.** The review rated 11 of the 20 round-1 findings resolved, 8
partial, and 1 resolved except for one new duplicate. It raised 13 new ones (N1–N13). I confirmed N1, N4 and N5 in the
code before revising.

- **N1, narration after the commit.** Revision 2's step 10 saved `runtime_state`, which broke "one save". Narration now
  lives outside the campaign document, in the narrative-response and narration-event tables. The commit writes a
  pending narration record atomically with the turn, and finalizing appends to it without a campaign save. §1 and the
  atomic test are restated.
- **N2, system-turn collisions.** Narration side effects are typed proposals that the next turn's load folds in, so
  they make no extra revision. A per-campaign turn lock serializes turns. `player_text` and `world_tick` turns run
  against the current state, and only view-dependent structured actions carry `expected_revision`. `system` turns are
  only the schema upcast.
- **N3, dialogue.** A `DialoguePlan`, decided by rules in step 3, sets what an NPC reveals and offers, and those
  become changes before the commit. The model phrases the line, and the fallback line is built from the plan. The
  world schema gains a knowledge section.
- **N4, replay storage.** A forward migration adds `document_version` and `pinned`. The upcast is its own revision
  with a turn row. Pinned snapshots are exempt from retention. RQ-0.9 audits patch gaps, and replay restarts at
  snapshots across them.
- **N5, concurrency.** The campaign revision is the only token; map and spatial counters are derived. NPC spatial
  state moves into the `npcs` section, so the hash covers it. World-tick turns have their own budget, and tactical
  moves have a 300 ms outcome target.
- **N6, outcome target.** It is split by whether the turn needs an intent call.
- **N7, statistics.** Each metric has its own denominator. The corpus has a frozen 1,200-item held-out set, the judge
  is calibrated (agreement ≥ 0.90, κ ≥ 0.70), the near-duplicate measure is defined, and the stretch thresholds match
  the sample sizes.
- **N8, effort.** Recomputed per lane: about 110 weeks in total, with a 60-week critical path in lane A. RQ-1.4 is
  split, so mechanics move in RQ-2 packages that each also consolidate their engine. Ticks move only in RQ-2.7.
- **N9, upgrade guard.** RQ-1.7 ships in a release before any v6 write. The per-mechanic settings are for
  development and the operator only.
- **N10, A1.** Replaced with a ratchet on cross-context imports that bypass contracts.
- **N11, retention.** Compaction into a pinned snapshot comes before deletion.
- **N12, stream route.** The submission-keyed route is named and added to the isolation tests.
- **N13, gate cost.** Gate model spend is budgeted in Q-6, along with when the model gates run.

**Revision 3 → 4 (2026-10-23), third review pass.** The reviewer verdict was "approve with changes". It found four
local design corrections, which I confirmed in the migrations and the persistence code before revising, plus two
schedule notes.

- **Narration storage.** `omnix_rpg_narrative_responses` is immutable and allows one row per turn, and
  `omnix_rpg_narration_events` is a short-retention transport table. So now:
  - the turn commits a `pending` row in the mutable delivery table (0022);
  - finalizing inserts the immutable response(s);
  - a forward migration keys responses by `(…, turn_id, kind)`;
  - continuity, the play screen and the journal read the response table;
  - RQ-1.1 moves every reader and writer of `narration_artifacts`.
- **Proposals and timing.** A turn records which proposals it folded in, and replay applies exactly that set. What an
  NPC was planned to say is in the committed `DialoguePlan`, so the next turn knows it while the narration still
  streams.
- **Turn lock.** The commit-time row lock cannot serialize whole turns without holding a transaction through model
  calls. It is replaced by:
  - a per-campaign FIFO submission queue;
  - planning outside any lock;
  - a short campaign row lock at commit, with a re-check that re-runs the deterministic steps 3–6 if the revision
    moved;
  - an in-request fast path only when nothing is queued ahead.
- **Hash and size.**
  - `state_hash_after` is a composite that covers each map-instance snapshot the turn touched.
  - The `npcs` section holds runtime cursors and positions only; authored routines, goals and knowledge stay in the
    world revision.
  - The spatial history tables stay outside the document, bounded.
  - RQ-0.9 measures document size before RQ-1.1.
- **Hermes.** Blocking narration waits for `narration.final`, with a timeout.
- **Schedule.**
  - RQ-5.4 waits for RQ-4.2.
  - The RQ-1.7 release is on the critical path.
  - Q-9's retention answer is no longer self-contradictory.

**Revision 4 → 5 (2026-10-23), fourth review pass.** The verdict was "approve once two contradictions are fixed".
Both are fixed:

- **Hash chain.** A composite `state_hash_after` would have broken the existing chain: `state_hash_before` is the
  document hash, and snapshots verify the document hash (`rpg_repository.py:357-361`). `state_hash_after` stays the
  document hash. A separate `maps_hash_after` covers touched map instances, and replay rebuilds them from map events.
- **Double fold-in.** A proposal chosen at load could be folded in twice by racing turns. The set is now chosen at
  commit, inside the re-check. A unique consumed marker per proposal makes it exactly-once, and the race is a
  playthrough scenario.

The reviewer found no other contradictions. It checked §1 against step 10, RQ-8.5, 8.6, 8.9 and 8.10, and the gate
set. The plan is approved. RQ-0 can start.

## 11. Status

Implementation runs on branch `rpg-production` in two lanes (§5): lane A in worktree `F:/LLM/omnix-rq-a` (branch `rq-a`), lane B in `F:/LLM/omnix-rq-b` (branch `rq-b`). Each package is merged into `rpg-production` after review.

| Package | Status | Commit | Evidence |
|---------|--------|--------|----------|
| RQ-0.9 | done; live run 2026-10-25 (owner's permission) | 44bb59d9e9 | `scripts/rpg_replay_audit.py`; 4 tests pass; scratch audit in `docs/measurements/rpg-replay-audit-scratch-2026-10-23.json`: no snapshot at creation (turns 1–19 unverifiable), new campaigns 1.7 MB from duplicated bootstrap/genesis snapshots; live audit (read-only, counts in `docs/measurements/rpg-replay-audit-live-2026-10-25.json`): 52 campaigns, 51 still `rpg-session-v1` documents, every turn row (119) without a patch and 314 revisions without a turn row, 13 snapshots all verified, no turn replaying to a different state: the live install runs the code from before patches and snapshots were kept, so nothing is corrupt and nothing older is replayable; the campaigns upgrade on load and record their history from then (all 52 upgrade in memory to the current document with this branch's upcasters, read-only check) |
| RQ-1.7 | done (desktop upgrade test lands with v6 in RQ-1.1) | cc477cbe22 | newer documents and save packages refused (503 `rpg_campaign_requires_newer_omnix`); migration 0170 `pinned` + `document_version`; retention skips pinned; `pin_current_state`; unit + PG tests pass |
| RQ-8.7 | done | 352e2dbdef | bundle assets lose `trusted_svg`/`curated-svg` markers on import (stored-XSS fix); SVG responses get a sandbox CSP; limits reviewed |
| RQ-8.3 | done (stream route joins it in RQ-6.2) | 23a6d4121e | gateway test, two signed-in users: list/read/turn/lore/rename/loadout/delete of the other's campaign refused, nothing written, drafts empty, workspace header refused; delete of an invisible campaign now 404 |
| RQ-8.2 | done | 736550271c | `OMNIX_RPG_TURNS_PER_HOUR` (default 600): 429 `rpg_turn_budget_exceeded` with Retry-After, counted in PostgreSQL across processes; unit + PG tests |
| RQ-8.10 | done | da8adac180 | archived campaigns purged after 30 days (all rows cascade); campaigns past 5,000 revisions keep the newest 1,000 turns behind a pinned snapshot; migration 0171; retention tests 10/10 |
| RQ-7.1 | part 1 done (layout/rails follow RQ-1.3) | 020a440da7 | Developer tools toggle (per browser) holds the Hermes execution result, sequence job panel and job ids; stubbed Hermes panels + ledger query removed; player wording; web 256/256, typecheck |
| RQ-4.6 | done | ea3c08a468 | `deterministic_rng` / `next_turn_id`; event injector, emotion variance, agent scheduler seeded; quest/choice/director ids and timestamps from the turn; AL013 scope widened, count 0 |
| (A1) | AL017 back to 0 | d6b5cd689d | environment simulation moved session → world; the genesis → session import from the published-world launch is gone |
| RQ-2.0 | done | 1990047be4 | `world_play_sections`: economy.providers, routines, knowledge, pressures, bestiary stats/behaviour/loot; authored economy played as written; authorship recorded; release findings block launch; tests 6/6 |
| RQ-4.2 | done (every-turn tick waits on RQ-1.4) | c5eab7c98c | published launches install a clock from authored pressures or derived road dangers; fixed the causal tick overwriting the turn (7f579fbf61); PG published-world play green |
| RQ-5.0 | done | 919ee62e13 | `docs/rpg/design/`: template, balance bands, rubric, notes for RQ-5.1–5.7 |
| RQ-7.4 | done | 79f60caa2d | the "legacy" wizard was the character step of the one flow: renamed `RpgCampaignCharacterStep`, dead starter-town branches removed, neutral hero defaults; web 256/256, typecheck |
| RQ-0.2 | done | f240bc8f65 | Aurelia golden, 30 turns + a tactical move, role-keyed scripted model; re-recorded on the world clock (no fact changed) |
| RQ-0.3 | done | 48d4af59ee | playthrough suite on Aurelia, Vesper-9 and the starter town: 44 pass, 20 strict xfail naming their packages; three bugs fixed (travel matching, companion names, second Vesper import) |
| RQ-0.7 | done | 1c3b67f090 | eight tests skip without a DB; `[rpg_turn_path]` = 512 modules from coverage over the suite; 101 RPG modules never imported, 477 imported but unexecuted |
| RQ-1.1 | done (narration-table move in RQ-1.4) | cee84e0da7 | document v6: 13 typed sections over v5 paths, one inventory (store wins), creation artifacts stored once (0180), upgrade as a pinned system turn on first load, package format 8; genesis campaign 1.9 MB → 203 KB |
| RQ-1.2 | done | e1bcb42c1c | 22 StateChange types, reducer with patch from writes; 450 seeded property sequences |
| RQ-1.3 | done for the turn route | 357667a053 | frozen TurnOutcome with changes, timings, model calls; changed_domains now real; web reads it; contract regenerated |
| RQ-0.1 | done | 39f83b58e5 | `scripts/rpg_scorecard.py` + ratchets in architecture_metrics (re-baselined at the RQ-1 merge, d1e9c2c87d) |
| RQ-0.4 | done | 47419da86c | 2,000-input corpus (800 dev / 1,200 frozen held-out), static + play harness with Wilson bounds; baseline in `docs/measurements/rpg-intent-baseline-2026-10-23.json` |
| RQ-0.5 | done | 6089ec649a | latency harness per turn class (Claude CLI Haiku N=20: look p50 14.6 s, question 2.0 s, fight 12.4 s); overhead rehearsal at 200 turns + world tick |
| RQ-0.6 | done (pilot n=180; full 900 is one command; judge uncalibrated until 150 labels are filled) | cd4c163e20 | baseline: correct speaker 0.28, near-duplicate 0.35, contradictions 0, leaks 0, turn failures 0.033 |
| RQ-0.8 | done | caa55226c2 | `docs/architecture/RPG_ENTRY_POINTS.md` + a test that fails on an unlisted mutating route |
| RQ-3.1 | done | c5f4d7b3ea | grammar on held-out: family 0.988 (lower 0.981), target 0.992 (lower 0.984); intent call skipped for confident deterministic families; clarifications without model calls; RQ-3.2 ambiguity scenario passes |
| RQ-3.3 part 1 | in progress | 8d98fbbbca | the person addressed answers; real-model pilot (n=60): correct speaker 0.28 → 0.675 (Aurelia 0.81, starter 0.80, Vesper-9 0.22), near-duplicate 0.35 → 0; open: Vesper-9 cast and starter people not in the scene view (RQ-2.0/2.8), `docs/measurements/rpg-narration-pilot-2026-10-24.json` |
| RQ-5.1 part 1 | done (defeat, battered, rest point, hardcore) | dbc963e614 | defeat: wake at last rest point (or the opening), +8 h, HP 25%, `battered` −2 attack until a full rest, purse −20% (≥1 c), seeded loss of the most valuable unworn non-quest item; hardcore ends the campaign (409 `rpg_campaign_ended`); open: injuries and flee costs (part 2); found: a second night's lodging and resting in the wild do nothing (strict xfails, RQ-2.3/2.4) |
| RQ-5.1 part 2 | done | 0410d79b31 | a blow over 40% of max HP wounds (−1 attack, heals at half) until a potion or two full rests; flee is d20 + quickness vs 10 + 2× the quickest foe's, success costs a parting blow from each foe standing at disadvantage (cut down while fleeing is a defeat); open: a healer's service treating wounds waits on RQ-2.3, potions on the published-world path on RQ-2.4 |
| RQ-1.4 slice 1 | look and wait on the pipeline | c6e64001e6 | `session/turn/`: TurnRequest, PlannedAction, pure resolvers, world tick (needs + the causal clock as `WorldTicked`), journal as `JournalWritten`, reducer as the only mutation; first stage of the session pipeline, `OMNIX_RPG_TURN_PIPELINE_LOOK/WAIT` (on); the outcome names `planned_action` and reports the pipeline's own changes; open: submission queue and commit re-check, pending delivery and narration out of the request, `maps_hash_after`, proposals, SSE events |
| RQ-1.4 slice 2 | narration beside the document | 7257e49bff | migration 0181 `omnix_rpg_turn_narrations` (campaign, turn, kind; newest 64 kept); every commit and save takes `runtime_state.narration_artifacts(_by_turn)` out of the document and loading puts them back, so a late narration is no revision (the RQ-1.4 xfail now passes); settings registered |
| RQ-1.4 slice 3 | turns in arrival order | 0b535ee52b | a campaign's turns run one at a time under a PostgreSQL advisory lock on its own connection (every gateway process shares it, no row held); a second tab's turn waits and runs on the state the first left, so both commit (the race scenario now requires 200/200); past `OMNIX_RPG_TURN_WAIT_SECONDS` (120) it is refused 409 `rpg_turn_in_progress`; open: accept-then-stream (needs RQ-6.2), the re-check against out-of-turn edits |
| RQ-1.4 slice 4 | early answers are turns | 5e9c428cf1 | an unclear command is planned as `clarify`: a counted turn in which no time passes, its question published as the turn's canonical prose with no model call (`OMNIX_RPG_TURN_PIPELINE_CLARIFY`); the RQ-3.1 ambiguity scenario now expects a committed turn |
| RQ-1.4 slice 5 | maps get their own hash | 1e70f72105 | migration 0182 `maps_hash_after` on turn rows: the hash of the map-instance snapshots the turn's transaction updated, in id order (NULL when none); exit criterion met (look and wait on the pipeline, golden and suite green); open for RQ-2/6: replay checking the maps hash, proposals (RQ-2.2), narration in a job and the SSE events (RQ-6.2) |
| RQ-1.5 | done (ratchets at today's counts) | f5e9f7a9b7 | AL018 saves outside the commit step 16, AL019 state writes outside the reducer 964, AL020 string-key section reads 735, over `[rpg_turn_path]`; baseline shrinks only, to 0 by the end of RQ-2; documented in RPG_CONTEXTS.md; note: `--check` still fails on 27 non-RPG entries (desktop, TTS swap) from main |
| RQ-1.6 | done | 48fa43a3d8 | the turn route's steps are `run_rpg_turn`; Hermes submits approved commands through `submit_rpg_turn` keyed by `submission_id` and reads the TurnOutcome; fixed: Hermes turns ran on an in-memory copy and were never committed; narration is still blocking in the request, so the wait for `narration.final` comes with RQ-6.2; the replay adapter runs no turns |
| RQ-2.7 slice 1 | idle resume is a world_tick turn | f3bde54f89 | `POST /api/rpg/sessions/{id}/resume` runs a `world_tick` turn through the turn route: up to 12 ticks for the time away, the causal clock ticks, no player turn counted, needs unchanged, a recap with no model call; TurnOutcome kind `world_tick`; the RQ-2.7 xfail passes in all three worlds; open: `/spatial-ticks` and the spatial runtime's port to the `npcs` section, deleting the unrouted idle-tick machinery (RQ-2.10) |
| RQ-2.7 slice 2 | one clock that moves | 51b150b302 | the world tick moves the simulation's environment by the turn's minutes (a tick is 10 min; look 10, wait 30, time away up to 2 h) with its weather, and the play screen's time follows; the clock stood at 09:00 on every path before; `docs/rpg/design/time.md`; found: a night's lodging taken in the morning sleeps 22 h (RQ-2.4) |
| RQ-2.1 | travel on the pipeline (worlds with a world model) | d7bbca7268 | grammar `move` to a place → `resolve_travel`: adjacency from the routes, the road's minutes on the clock, presence at the destination, quests advanced and paid (`rules/quest/arrival.py`), refusals as the game's own line; the reducer's `LocationChanged`/`PresenceChanged` keep every location mirror (simulation, sheet, title, region, scene) and the party moves with the hero; turn-start campaigns are hydrated as the older path did; golden facts unchanged; `OMNIX_RPG_TURN_PIPELINE_TRAVEL`; open: the starter town's travel (RQ-2.8), map actions, deleting the older travel path when every caller is moved |
| RQ-2.3 interim | purchases on the pipeline through the old service resolver | b5487a2aa2 | buy/inquire for goods, meals, drinks, lodging: the resolver runs on a copy, its effects become typed changes + `TradeRecorded`; facts unchanged, one model call per purchase instead of two; to be replaced by a clean trade engine on the economy section (owner direction 2026-10-24: rewrite rather than wrap legacy) |
| RQ-2.3 | trade engine (buy, list, sell) on the economy section | 9d55a74ec5 | `rules/economy/trade.py`, pure: offers of the people here, matched by the player's words; price, stock, purse checked; goods, a meal's or drink's relief, a room reserved, the stock left and the trade in the ledger as typed changes (`ServiceReserved`, `StockTaken`, `TradeRemembered`); sell-back half for the shop's own goods, 5 c otherwise, nothing for quest rewards; the interim wrapper and `TradeRecorded` deleted; one model call per trade; open: paid information and repairs (with RQ-2.2/2.4), price pressure from the causal economy (RQ-4.4), deleting `player_requests` and the service path once their last callers move |
| RQ-2.4 | items and rest on the pipeline | e94d52feac | `rules/interactions/items.py` (use: a potion heals 30% (≥10), halved while wounded, and closes the wound; food and drink ease needs; drop and pick up) and `rules/rest.py` (a room paid for, a camp, a while; full rests set the rest point, end battered, rest wounds; no sleeping in the street where rooms are rented); `docs/rpg/design/items-and-rest.md`; one resolution dispatcher (`session/turn/resolution.py`) and one setting `OMNIX_RPG_TURN_PIPELINE_OFF`; three strict xfails now pass; owner direction (2026-10-24): rewrite each mechanic as its own rule and delete the legacy it replaces rather than wrap it |
| RQ-2.5 part 1 | quests, practice, status, party on the pipeline | adbe9134fe | `rules/player/requests.py`: taking a quest, practising (legacy curve until RQ-5.3), status read off the campaign with no model call, joining and leaving the party, standing orders to companions (grammar `order` family, `CompanionOrdered`); load normalizes progression defaults; the companion-order xfail passes; open: quest offers in conversation (RQ-2.2), deleting `player_requests` once the starter town is a bundle (RQ-2.8) |
| RQ-2.2 | dialogue: rules decide, the model phrases | 4a9ef3b0c3 | `rules/dialogue/plan.py`, pure: the speaker's canon, stance from trust (friendly ≥ 50 or companion, wary < 0), knowledge facts matched to the player's words (freely / when trusted / for a price / never), a quest offered when asked for work, wares with prices (sold-out goods left out); `KnowledgeShared`, `QuestOffered`, `DialogueExchanged` before the commit; one call (`rpg.ai_compact_dialogue.plan`) writes the line, which is refused for a secret or a missing ware and replaced by the plan's own line; the narrative engine adopts it keyed by the interaction; the older path's dialogue-quality rewrite (45-word floor, stock Bran lines) no longer touches pipeline turns; published worlds carry personality, speech style, goals and secrets; every route returning a campaign returns the player view (no world model, campaign bible, NPC index or setup payload: they reached the browser before); found: the production-turn golden had not been re-recorded since RQ-1.3; since look moved to the pipeline (RQ-1.4) a starter campaign's first look skips the older path's first-turn world setup, so "talk to the bartender" finds no one and goes to the intent router (two calls): re-recorded as is, fixed by RQ-2.8 (starter as a bundle); open: speakers the world model does not know take the older path |
| RQ-2.8 slice 1 | the classic new game plays from the starter world | 71e0e9beb5 | The Market Road (`resources/examples/rpg/world-bundles/the-market-road/`): the Rusty Flagon content gathered from the engine's five inconsistent copies (location graph, location registry, biographies, schedules, goals, rumors, service registry, encounters) into one readable source with RQ-2.0 sections, 7 grid maps and 5 openings; `genesis/worlds/world_source.py` compiles it with the real compilers (revision, certified release, map definitions, scenarios) into a deterministic bundle (`materialize.py` writes it to a file); `genesis/worlds/builtin_worlds.py` builds, imports and adopts it on first use under a content-addressed id and `create_new_game_session` launches the opening for the starting place, the chosen hook's quest first and the player's own gear kept; places author their environment (climate, opening weather, exposure, temperature) and aliases; bundle archives are stamped with the export time; the starter's travel, companion, trade, lodging and one-call-question scenarios pass (5 xfails removed), and "talk to the bartender" is one dialogue call again; next: bind v5 starter campaigns to the bundle (slice 2), the Glimmerdeep demo bundle (slice 3), delete the literals and add the A4 lint (slice 4) |
| RQ-2.8 slice 2 | old starter campaigns play in the starter world | b533cad9da | document version 7: a campaign of the starter town (bound "starter" by v6, or unbound at v5) has the ids the engine's copies used (`loc_tavern`, `npc:Bran`, `npc_innkeeper`: the world source's `legacy_ids`) rewritten as whole values, the world model for where the hero stands, who is present there and the scene, and a binding naming the starter world (`builtin_worlds.bind_to_starter_world`, pure: the model is compiled from the source); a World Forge campaign the v6 upgrade also marked "starter" is marked "genesis" instead; every new document states its binding at birth (`genesis` or `unbound` until a world's launch binds it), so the upcasters never bind a fresh campaign; the playthrough upgrades a pre-bundle classic campaign and plays it (talk, travel, trade); dialogue offers only the wares the player names, and a line names a ware by a word of its name |
| RQ-2.8 slice 3 | the demo is an opening of the starter world | 9e688efe48 | the Glimmerdeep demo was a hand-built document in `new_game.py` (deleted); The Market Road now reaches north past Glimmerdeep Pass (Frost Haven, Frostpine Hollow, the Northern Watch, the Glimmerdeep: 4 places, 4 maps, 5 people, a seller, 3 quests, the Icefang) and its demo opening (`metadata.preset_id`) starts a campaign under way from the scenario's `starting_resources`: the hero's level (sheet and simulation), equipped gear, kit and purse, the party (as companions following the hero), standing with people, the quests already taken up, the journal so far and the turn it starts at (`published_launch._continue_in_progress`, generic: any world can author one); presets are listed from the world; the starting turn is the sheet's, not the campaign's revision; the playthrough starts the demo and plays it (talk, travel with the party) |
| RQ-2.8 slice 4a | the A4 lint | c18e7fe685 | AL021: a string in `rules`, `world`, `session` or `narration` (docstrings aside) that names the starter world's people or places, or the ids the engine's old copies used, counts per module and name; the watchlist is `[rpg_world_content]` in `layers.toml`; baseline 320 in 56 modules (Bran 116, loc_tavern 35, rusty_flagon 32, Elara 30, Mira 24, ...), only shrinking; the registries behind them (services, biographies, locations, rumors, schedules, map fixtures, climates) go with the older path that reads them (RQ-2.10) |
| RQ-2.6 part 1 | fights on the pipeline | 095bc74f92 | `rules/combat/fight.py`, pure and seeded: a creature of the world's bestiary (no default foe) is fought: initiative, blows (d20 + accuracy − condition penalty vs defence, damage less armour), heavy-blow wounds, breaking away with parting blows, everyone else's turns; victory earns each creature's experience (or 25 a level) and its bestiary drops into the one store, with level-ups; defeat is the stakes setback as typed changes (or the end in hardcore); in a fight the hero strikes, flees or uses something carried (their turn, then the others'), and leaving, resting, trading or talking is refused in the game's words; the party's health is the party's, so a heal between blows holds; new changes `CombatAdvanced`, `CompanionHpChanged`, `LevelReached`, `DefeatRecorded`, `CampaignEnded` (39 types); `docs/rpg/design/combat.md`; found in the old runtime: loot went to a third inventory from a built-in bandit table and walked past the world's bestiary; open (part 2): abilities, ammunition, orders mid-fight, fighting people, the tactical grid as a structured-action producer, deleting the session's combat modules |
| RQ-2.6 part 2a | the grid is the same fight | 5937dfb8d5 | the tactical routes submit structured-action turns (`session/turn/tactical.py`) with the campaign revision as the only token: a grid move spends the hero's movement for their turn (60, fresh each turn) and its map event is written in the turn's unit of work (so `maps_hash_after` covers it); a grid attack is the fight rule's blow, the target's cover adding to its defence and a blocked line of sight or a target out of reach refused; a refused grid command takes no turn; `TurnOutcome.action_result` carries the route's answer; `tactical_spatial_service.py` (its own commits) and the second attack engine in `tactical_spatial.py` (budgets, reactions) are deleted, leaving the grid's rules (movement, cover, reach, the grid's view of the fight); the observer read the fight from the wrong place and never showed the hero's turn; the tactical xfail passes; the web contract, stale since RQ-2.3, is regenerated (web typecheck not run) |
| RQ-2.4 part 2 | one gear record; the loadout's pack actions are turns | 6f7779f065 | wearing and wielding (`items.equip_item`, `unequip_item`, grammar `equip`/`unequip`) on the pipeline; what is worn is the store's (`inventory_state.equipment` by slot), which combat now reads without writing (it read, and created, a third record in `player_state.inventory`), and the reducer mirrors the sheet's list; gear that leaves the pack is no longer worn (a sold dagger stayed on the sheet); document version 8 gathers the old record into the store (`foundation/state/gear.py`); the loadout's use, equip, take off and drop are structured-action turns with the game's own lines (no model call), a refusal takes no turn; open: crafting, salvage, modifications and abilities in the loadout, and the legacy item modules that still write `player_state.inventory` (RQ-2.10) |
| RQ-2.1 part 2 | the world map is the world's own, its journeys turns | ceb3c03cd1 | a published campaign's visual map was the built-in fixtures' Northern Pass and Frost Haven (another world's places); its world graph now comes from its world model (places, regions, roads, where the hero stands and has been, and where the roads from here lead), the fixtures serve only a generated campaign's kept graph, and the map follows the hero (`map_world_integration.world_graph_source`); a journey or an entering chosen on the map, to a place the world knows, is a structured-action travel turn (it moved only the sheet, not the simulation), a road that cannot be taken refuses the request with no turn; looking at the map saves nothing |
| RQ-2.7 slice 3 | the world's people keep their day; /spatial-ticks is a world_tick turn | 3d2e8419dd | the routines every published world authors (`canon.routines`, compiled into the world model) were read by nothing, and who was present at a place never changed; `rules/routines.py` (pure) says where each person is at the clock's time: away from the hero where their day puts them, in the scene with the hero until their day turns to its next part, companions with the hero, no routine where they are; the world tick records it (`WhereaboutsChanged`, 40 types, in the `npcs` section's index) and who is present where the hero stands, and the hero sees the comings and goings ("Captain Aldric arrives, keeping order in the square."); travel and a defeat's waking ask the same rule; `docs/rpg/design/routines.md`; the older spatial runtime (its own clock, goals, routines, policy and tick tables outside the campaign; no caller in the web app or any world) is deleted with its goal, routine and policy routes; `/spatial-ticks` runs 1 to 12 ticks as a `world_tick` turn and `/spatial-state` reads the whereabouts from the campaign; `/continue` only loads (no move); migration 0027's tables retire by a forward migration after a release; `RPG_ENTRY_POINTS.md` brought up to date for the tactical, loadout and map-action turns; found: runtime lore names a place after its id ("Location:Market Road:Market Square was encountered at Market Square.") and the narrator is told it |
| RQ-3 fix | a turn's target speaks only when it is a person | e74abd590a | the narration bridge took any turn's `target_id` as the speaker and made it an NPC id (`npc:location:market-road:market-square` for a journey), so runtime lore materialized a person named "Location:Market Road:Market Square" and grounding published "...was encountered at Market Square." as the turn's first block; a typed id of another kind (place, item, offer, creature) or a non-person `target_kind` now names no speaker |
| RQ-2.8 slice 4b | the wizard's campaign without World Forge sets out in the starter world | 6607e59cd5 | §4.4: a creation-wizard campaign with World Forge off was the engine's built-in tavern (another copy of the starter town in `new_game.py`, with no world model, so no pipeline mechanic ran in it); it is now the starter world's opening for the chosen place and hook, with the wizard's hero and genesis attached (`pipeline_adapter._launch_in_starter_world`); a published launch builds the campaign and saves it once, opened (it saved the base campaign first; `prepare` lets the caller add its records before that save), so a campaign starts at revision 1; the launch kept the world's seed over a new game's seed of 0, and recorded "published_opening" over the hook the player chose; fixed since earlier slices: a tool (compass, lantern, torch) is held to hand (`tool` slot), the persistence integration tests follow the loadout turn and the dialogue plan; open, for the owner: a World Forge campaign has no world model either (it plays on the older path and the starter registries), while the world library's generator already makes worlds from World Forge output, so §4.4 calls for the wizard's World Forge campaign to generate a world and launch it, which is not yet a work package |
| RQ-2.6 part 2b | fighting people, and defending | ec6618af0d | a person present is fought by the fight rule (it took the older engine): their numbers from what they do (fighter, hardy, anyone else), the one attacked and everyone who sees it trust the hero less (`RegardChanged`, 41 types: -40 and -15 on the trust dialogue reads; the play screen's relationships show it), beaten they yield, alive, for no experience or spoils; a companion is not turned on; in a fight the hero can defend (+2 defence until their next turn); `combat.md` updated; open: abilities, ammunition, orders mid-fight, grid reactions and placement, deleting the older engine |
| RQ-2.6 part 2c | the hero's abilities in a fight | f548ca974e | `rules/ability_use.py` (pure): an unlocked ability by name, hotbar slot or id, ready once its cooldown in the hero's turns is over and paid in stamina or mana; its effect operations say what it does in a fight (a health-damage effect is a sharper, harder blow; a heal; a negative enemy check hinders the target's blows for its turns); aimed at a foe it opens the fight; the hotbar in a fight is a structured-action turn of the same rule; new changes `ResourcesChanged`, `AbilityUsed` (43 types; the play screen's cooldowns kept as turns left); a night's rest restores stamina and mana (nothing did); found: a bare "attack" in a fight took the older engine (the grammar read it as a lone verb, and planning dropped it), and the hero's turn line came before the blows that fell before it; open: abilities' world effects out of a fight (the older ability runtime), ammunition, orders mid-fight, grid reactions and placement, deleting the older engine |
| RQ-2.9 | the registry test | bccbcade7b | `test_mechanic_owners.py`: each mechanic on the pipeline has one owning rule (checked against `PipelineMechanic` and the pipeline's imports), and each of the 43 changes, reduced on a real campaign, writes only the sections it is declared to (`CHANGE_WRITES`, from the sections' own `SECTION_PATHS`): a second writer of a section, or a path no section owns, fails it; writes outside the reducer on the turn path stay AL019's; found: the trade ledger and stock, kept services, dialogue memory and focus, the campaign's end, the scene and the older readers' location copies were owned by no section (now economy, npcs, meta and location), and a move wrote the presence list too (presence is `PresenceChanged`'s) |
| RQ-3.4 + RQ-8.1 | the world's text is data, and an obedient model gains nothing from it | 2a9ddc91f8 | `narration/world_data.py`: world-authored text in a prompt is fenced (`<<<WORLD_DATA` ... `WORLD_DATA>>>`, a fence inside the text cannot close it early) with the rule that it is never an instruction; the dialogue plan's line prompt fences the plan (template v2), and the narrative writer's system prompt says the world's text in its evidence is material, never instructions (v3); `test_untrusted_world_text.py`: a world poisoned where its authors write (a place, its people, a secret) and a model that obeys it (it gives the secret away and hands out gold): the purse, pack, quests, place and peace stay the rules', the secret is never shown (the plan's own line replaces the one that repeats it) nor stored in a turn, and the world's words reach the model only inside the fence; open, for RQ-3.3: verifying the narrator's claims against the outcome (a narrator that says "you receive 1000 gold" changes nothing, but the prose is not yet checked) |
| RQ-8.9 | a view the campaign moved past is refused with how it stands | fe9519107b | `edge/api/stale_view.py`: a grid command naming a campaign revision the campaign has moved past, or a map action from an outdated map view, is refused (409, no turn taken) with a plain message, the current revision and the campaign as it stands (the player's view), so the play screen redraws; typed turns from a second tab run on the current state in arrival order (RQ-1.4 slice 3); both are in the suite |
| RQ-8.8 | the storyteller down or too slow | 0092cb95d1 | a call kind's limit holds (the RPG gateway passed none to the provider; a person's line has 20 s, the writer its deadline); failed model calls are counted apart (`model_calls.current_model_failures`), and a turn with one carries the notice that the storyteller is unavailable (`notices` on the turn response; the play screen shows it as a line from Omnix); found with a failing provider: a person's fallback answer spoke their profile card ("Orik Stonewake Id: npc:... Name: ... Role: ... Goals: ..."; the speakable check read only a card's first line), a command the grammar could not read showed its reason code ("no_supported_semantic_action_detected"), and the fallback named people from their ids; the deterministic writer's starter-world lines (Bran, Vexira) are gone; `test_storyteller_outage.py`: with every call failing, grammar commands play by the rules, travel moves the hero, the player is told, and nothing shown is a card or a code |
| RQ-8.5 | a crash mid-turn leaves the turn or none | 3ac67f3cc9 | `test_crash_mid_turn.py`: the gateway stops at each step of the turn route (before anything runs, after resolving and narrating, inside the PostgreSQL transaction once the turn row and narration are written, and after the commit at every later step): the campaign holds the whole turn (revision, turn row, canonical narration, committed together) or none of it, and the client's retry with the same submission id commits it exactly once or answers from its record; found: a turn that failed before its commit marked its submission failed for good, so the retry was refused ("foreground submission failed") and the player's turn could never be taken; a failed submission committed nothing, so a claim now takes it over and runs it again |
| RQ-3.3 part 2 | the narrator says only what the rules did | bb8d548d6d | the validator refuses prose that states an amount of coin, experience or health, a level, or a thing gained or lost by name that the turn's evidence (its outcome and scene) does not hold (`unsupported_material_claim`); the response is repaired, revised with the feedback, or replaced by the game's own lines; found: a writer that added "You receive 1000 gold and a Crown of Kings" to a look was published as written |
| RQ-5.2 part 1 | checks outside a fight | 2a8f82f237 | `rules/checks.py` (pure, seeded): persuade, intimidate, deceive, sneak, climb, pick a lock, recall lore, search and notice are a d20 + skill rank + attribute modifier + situation (+2 trusted, -2 wary, less condition penalties) against the target's difficulty (the world's, else moderate 13; +2 for the same try again, here, within two hours); the margin's band (strong, success, at a cost, failure; a natural 20 at least a success, a natural 1 at most at a cost) decides what follows: regard won or lost, the trust of those who notice a sneak or a jammed lock, a hard climb's scrapes, a creature's weakness recalled, what lies here found; a success earns the skill's experience by difficulty; `CheckResolved` (44 types) keeps the last 20; the grammar's `check` family (the held-out corpus's labels kept: a search stays a manipulation of the scene); `checks.md` "as built"; open: the shopkeeper's discount, a noise's pressure, the outcome card's roll (RQ-7.2) |
| RQ-5.3 part 1 | one experience curve, and each level's choice | d94befcde1 | `rules/player/progression.py`: one curve for every source (100 x n to rise from level n), each level 5 health plus the constitution modifier and a choice that waits without blocking play (+2 to an attribute, an ability the level allows, or a rank in two skills; `LevelChoiceMade`, 45 types; the grammar's `grow` family); skills 0 to 5 at 50 x (rank + 1), an hour's practice 5; found: quests paid no experience on the pipeline, checks and practice used another curve, and only the fight rule ever raised a level (a quest's experience never did); quests now pay what they name, else 100 a place, checks 5 to 35 by difficulty, a first visit 15; `progression.md` "as built"; open: the 500-turn balance simulation (the package's exit), the choice on the play screen (RQ-7.3) |
| RQ-5.3 part 2 | the balance simulation | 8245bea612 | `scripts/rpg_balance_sim.py`: a deterministic reasonable player plays 500 turns on the pipeline's rules in memory (the README's policy: flee when losing, sleep a night when hurt, eat or buy food when hungry, take every quest and walk its places, fight the world's creatures, make each level's choice); `test_balance.py` in Aurelia and the starter world: level, fights won, defeats, time hurt and hunger inside their bands, every command played by the pipeline; found: the hero's level never made them better in a fight (their numbers were their gear's alone; a level-5 hero fled level-3 creatures half the time): accuracy, damage and defence now count level and attributes, tuned; quests that name no experience pay 50 a place (from 100); outside their bands, tracked as a strict xfail: the purse (no coin once the few quests are done, RQ-5.5), quests completed (side quests, RQ-5.4), the late win rate (a fixed bestiary the hero outgrows, RQ-5.6) |
| RQ-5.7 | undo and save points | 498bb91727 | `POST /rewind` is a structured-action turn: the revision before the hero's last turn (past world ticks, upgrades and earlier rewinds, `session/turn/rewind.py`) or a save point's, rebuilt from the nearest snapshot and the turns' patches with every hash checked (`rpg_repository.document_at_revision`), its game put back as a new revision (`RevisionRestored`, 46 types: the sheet, the simulation, the game's runtime sections, the turn count; the bookkeeping goes on, so history is never rewritten); save points as named pinned snapshots (migration 0183, at most 20, `POST/GET /save-points`, `DELETE /save-points/{name}`); none of it in hardcore; turn rows record their kind (`turn_kind`, `restored_revision`); found: a campaign's first revision and every revision written outside a turn had no snapshot and no patch, so the history could rebuild none of them (an undo early in a campaign was impossible, and the replay audit had gaps): each now keeps its document; open: the undone turns' narration marked superseded, the play screen's buttons (RQ-7) |
| RQ-5.4 part 1 | quests of several steps, with branches, deadlines and failure | 6c139ab98c | `rules/quest/progress.py`: a world authors a quest's `steps`, each `all_of` conditions or `any_of` branches (reach a place, talk to someone, about something when it says so, hold an item, defeat a creature a number of times, pass a check), judged after every turn's changes and world tick and after time away; `QuestProgressed` and `QuestStepCompleted` (48 types) keep the tallies, the stage, the branch taken and the next objective; the last stage completes the quest with its rewards (coin, items, XP: named, else 50 a step); `deadline_hours` from `accepted_at_minute` fails it and costs the giver's regard 10; the starter world authors three (the tavern rumor's two ways, the cellar's three rats then the report, Elara's job within a day); found: a quest's outcome said on a dialogue turn was never shown (the person's line was the whole response): what the exchange led to is now said after it; a bare talk condition took any word to the person (asking Bran about the weather answered the rumor): a talk names what it is `about`; the quest a campaign starts on now has its taking-up time, so its deadline runs; open: other fail conditions, pressure side quests (part 2) |
| RQ-5.4 part 2 | the world's pressures raise side quests, and the hero's deeds push them back | 6bf53faca1 | levers have a grammar checked at release (`defeat:<creature>` for each felled, `quest:<quest>` when completed); `rules/pressures.py` pulls them after the quests move, as one replayable `lever_pulled` event in the causal runtime (`pull_levers`; `PressuresMoved`, 49 types); the pressure of the hero's region at 60 or more raises a side quest, offered by a fitting person with the hero (guard, captain, guild...): its strongest lever creature up to two levels above the hero, as many as ease it by 20, then a word with the giver, 10 silver (`QuestOffered` carries the new row); none of it on a refusal, a question back or a rewind; the balance simulation does quests of steps; found: nothing ever pulled a lever, so every pressure only rose; the starter world's levers were prose no rule could pull (now in the grammar); accepting a side quest offered again under its title took the completed one and was refused; the simulation's player repeated a conversation it could not play forever (taken as answered); purse and quests done now inside their bands; open: the win rate (late, and early in the starter world: RQ-5.6), a pressure as a step condition, other fail conditions |
| RQ-5.6 part 1 | creatures act like themselves | e080f7a532 | `rules/combat/fight.py` `_behaves`: a creature that flees when hurt tries once below 30% on the hero's own rule (got away: nothing earned, `enemy_fled`); one that calls allies does once below 50%, answered on a seeded even chance by one more of its kind; guardians do not pursue (breaking away always succeeds, no parting blows); an ambusher strikes first; behaviour reaches the fight from the catalog, and a world that names none has it derived from the creature's name and traits (Aurelia: the Echo Wolf flees, the Rootbound Knight guards, the Glass Wight ambushes, the Hollow Archon calls allies); balance win rates now inside their bands in Aurelia and late in the starter world; found: nothing ever restocked (an inn let six nights, then was sold out for the campaign): stock grows back by `restock_per_day` from the day of the sale, a rate-less offer each day afresh; a side quest's hunt took creatures that, with allies called, outmatched the hero, fell back to far stronger ones when none fitted, and at level 9 sent the hero after the world's boss: it now takes the strongest below the hero's level, else their equal, never a boss, no offer when none fits; the balance simulation's player rented rooms it could not afford forever (it now checks the price); pending, each a strict expected failure: Aurelia's late purse (RQ-5.5), the starter world's early win rate; open: negotiation and stealth (part 2) |
| RQ-5.6 part 2 | the road's dangers, slipping past and talking down | de056d1c87 | `rules/pressures.py` `road_encounter`: arriving where no one lives in a region whose pressure is above 40, a seeded chance of the severity above it puts one of the pressure's creatures (fitting the hero, never the boss) in the way, on the typed journey and the map's (`met_on_the_road`); the creature bars the way and the hero chooses first (an ambusher strikes); before blows, a sneak against the foes' best defence less 2, or persuading or intimidating at hard (16) for a person or a creature that speaks (authored or derived from its lore), ends it with no blow struck; after blows it is a fight; the grammar reads "reason with", "talk it down", "parley" as persuading; the playthrough harness breaks away from what the road brings (`clear_the_road`); found: a check easier than the easiest difficulty had no experience to pay and raised |
| RQ-5.5 | prices that answer the world, a haggle, and sources that last | d4feb83aef | `trade.price_of`: +25% when an offer is nearly gone, +20% when the seller's region's trade access is below 40, -10% from a trusting seller, -10% for the day after a haggle won (a check of its own, `haggle`), each named on the purchase; checks record their clock minute; selling at the authored fraction was RQ-2.3's; side quests from the pressures one at a time, at most one a day, the hero's region first else the most severe elsewhere; found: a felled creature pushed back every region's pressure that listed it (Aurelia's derived pressures list every creature everywhere), so one march's wolves made the whole world safe by turn 250 and nothing paid after: a `defeat:` lever pulls only its own region's pressure; the balance simulation's purse is now inside its band in both worlds and every one of Aurelia's measures is; pending, a strict expected failure: the starter world's win rate (its bestiary has little between levels 2 and 9) |
| RQ-4.4 + RQ-4.5 | the world keeps its own time, and word of it reaches the hero | 7a07eb6af6 | the causal runtime ticks once for each hour the clock crosses, at most 12 at once (`world_tick.MAX_PRESSURE_TICKS`), so time away catches up capped and a fight's blows move no pressure; a pressure escalating, held, ended or stirring again is told in the turn's lines and the time-away recap, the hero's region first, at most two a turn; what the hero does to pressures was RQ-5.4's levers; found: every turn was one pressure step whatever its time (a twenty-round fight moved each pressure as twenty journeys); the balance simulation's player now sells the spoils it carries (the starter world's hunter keeps its roads below the side-quest line, and its potions are its income) |
| RQ-4.3 | a person's goals lead what they say and offer | 960bb32bc3 | the routines' authored goals lead the `DialoguePlan`'s goals (touched by the hero's words first, then by priority); of the quests a person could offer, the one closest to the hero's words and then to their most pressing goal (it was the first in the log); asked about what a goal of theirs is after, they offer the quest that answers it; who is present follows routines since RQ-2.7 slice 3 |
| RQ-7.2 | the outcome card | 111cc4e2ea | `narration/presentation/outcome_facts.py`: the turn's changes as plain facts with a tone (coin, items, health, the hero's conditions, experience, level, quest steps, completion and failure, offers, the dice of a check, trust, how a fight ended), named from the campaign as the turn left it; `TurnOutcome.presentation.facts` (contract regenerated); the play screen shows them after the turn's lines as one chip per fact, gains and losses apart (`RpgStoryScene`, `RpgOutcomeFacts.css`); open: the card is the live turn's, a reloaded transcript does not rebuild it |
| RQ-7.3 | suggestions as chips, a question's answers as choices | 0ff9720b2c | `session/turn/suggestions.py`: after each turn, what the scene offers (in a fight its moves, and before blows slipping past and talking down; else the people here, an offered quest, a seller's wares, the roads out, a look around; at most 6), and when the game asks, the answers (who to attack, where to go, who to speak to); `TurnOutcome.presentation.suggestions`/`choices` (contract regenerated); the composer's chips take the latest turn's (`rpgTurnOffers.ts`), its choices first; found: the play screen's suggestions were written once at launch (`quick_actions`) and never changed, so it offered "Talk to Bran" wherever the hero went |
| §7 owner decisions, 2026-10-25 | answered | — | the wizard's World Forge campaign generates a world and launches it (option a); the older turn path and the registries it reads are deleted (RQ-2.10); the replay audit ran on the live database (RQ-0.9 row) |
| RQ-2.8 slice 5 | a World Forge campaign plays from a world of the library | 78d939358e | owner decision (option a): the genesis job makes the campaign's world by the library's own lifecycle and gates (`genesis/forge/wizard_world.py`: the world, its profile approved by the wizard's submission, its lore generated by the library's jobs and signed, accepted, published and certified, an opening prepared) one resumable step at a time, deferring itself while the library's workers generate, and launches the campaign from the opening the wizard named under the id it gave the player (`launch_published_scenario(session_id=...)`); without the job queue the request is refused (`campaign_world_forge_requires_queue`); deleted: the campaign-scoped World Forge that materialized lore into the campaign (`world_forge_pipeline`, `materialization`, `world_forge_commit`, the background expansion job, which is retired when an old one is claimed, and the campaign-only planning modules) with their tests; found: the compatibility route's classic new game ran a full World Forge (the promoted contract named no `world_forge`, whose default is on), now off; the save-point routes published no typed response (`RpgSavePointsResponse`); `rules/pressures.py` imported the world layer (AL017): the turn now gives the rule the runtime's pull; open: the end-to-end run with a real model (the deterministic generator's worlds do not pass the library's publication gate; this machine routes World Forge to LM Studio, which was not running), the wizard's progress labels for the new stages (RQ-7) |
| RQ-3.2 | the pipeline answers every command; one intent call when the grammar is not sure | 2124e43954 | `session/turn/intent.py`: a command the grammar cannot read with confidence gets one structured call (`rpg.turn_intent.readings`, temperature 0, 10 s) returning up to three readings, each kept only when its family is one the pipeline runs and its target is in the scene, of a kind that family takes; the best is planned like the grammar's, two within 0.15 make a question whose answers are the two commands (choices), none trusted (below 0.5) is a free action (`act`: ten minutes, nothing the game keeps); in a fight an unread command is a blow; with no storyteller the turn asks again and nothing happens; the older turn path no longer runs a player's words (`OMNIX_RPG_TURN_PIPELINE_OFF` removed; its stages are deleted with RQ-2.10); items on the ground are in the scene; found: a model reply that was JSON or held no words (`{}`) was published as a person's line, now the plan's own line answers; the production-turn golden's talk turn is now a pipeline turn (it counts and takes its time) |
| RQ-2.0 lore worlds | a world written as lore plays from its lore | 2124e43954 | `genesis/worlds/lore_sections.py`: Vesper-9 keeps its people, regions, places and threats as canon entities and lists places by id with no roads; launch now reads the authored section, else the entities of its kinds (a person's role from their summary, goals and secrets from their lore; a threat's level, capabilities and weaknesses), a bare place filled in from its entity, and roads derived from the regions (each place to the others of its region, the regions joined through their first places, 30 minutes); threat words situational/variable/dangerous/elite mapped; Vesper playthroughs: travel, asking the courier, fighting the Nullborn and the inventory round trip pass (shops and lodging stay strict xfail: the world authors none) |
| RQ-2.10 | the older turn path, and the code nothing reaches, deleted | 610b370a47 | owner decision (delete the old code): a turn's stages are three (`session/pipeline.py`: the planned turn, its commit, its lifecycle); the older core (`interactive_first_call_runtime`) and its stages (fast dialogue, dialogue quality, combat presentation, visible response, player agency) are gone, and what the pipeline cannot run is refused with no turn (`rpg_turn_empty`, `rpg_turn_kind_unknown`, `session_not_found`); an `rpg.turn` job runs the turn route's steps (`edge/api/turn_job.py`, `submit_rpg_turn` keyed `job:<id>`) and one with no campaign fails instead of asking a model for prose; then every top-level name and module that neither the gateway, the feature's roots, the scripts nor the tests of live code reach (symbol-level, through imports, aliases, lazy exports and dotted strings) is deleted: 337 of 1,149 RPG modules, 94.5k lines, with the 56 test files that only tested them (social, spatial, causal memory, the older response generator, the choice, quest and combat engines, save packages' unused builders, the turn-context id seeding nothing bound); the stakes tests the older combat runtime carried now run on the fight rule; ratchets: AL018 16 -> 3, AL019 953 -> 426, AL020 733 -> 252, AL021 318 -> 198 (the rest is in live code: open), `unreachable_rpg_modules` 0; the endurance gate of the older composition and its CI job removed; the intent eval's static reading is the campaign's grammar reading; the intent template is registered (missed in RQ-3.2) and 25 dead templates are gone; contract unchanged; found failing before this change: `test_world_mechanics_change_real_state` and the runtime-retirement bootstrap (fixed next) |
| RQ-6.1 | the call budget, asserted | 38602183fe | the latency harness on the route (Claude Haiku via the CLI, n = 2 a class, `docs/measurements/rpg-latency-route-2026-10-25-n2.json`): every turn made one call or none, but waiting asked the narrative writer (11 s) and one fight's writer was asked twice (35 s); waiting is now the game's own line (no call); `test_the_turn_mix_keeps_its_model_call_budget` asserts F3 on the harness's mix (deterministic turns none, none over two, at least 80% at most one) from each turn's counted calls; the harness marks the outcome at the `planned_turn` stage (the older `resolve` stage is gone); F1 open: look 14 s, arrive 21 s, buy 8 s, fight 14 s complete, first narration 5-10 s, all model time (overhead about 250 ms): RQ-6.2/6.3 stream the outcome first and the narration, RQ-6.5 shortens the writer's prompt |
| RQ-6.2 + RQ-6.3 | the turn stream: the outcome at the commit, the narration after | 39c5a02248 | `docs/rpg/design/turn-stream.md`: with `X-Omnix-Rpg-Turn-Stream: 1` a turn the writer must narrate commits with no narration and answers at once (TurnOutcome, the outcome card, `narration: pending`); the writer narrates beside the request, its drafts on `GET /api/rpg/sessions/{id}/submissions/{submission}/stream` (`accepted`, `committed`, `outcome`, `narration.delta`, `narration.final`, `error`; `Last-Event-ID` resumes), the response inserted with no campaign save, and reading the campaign fills each recent turn's narration from the response table; turns whose words are written (the game's, a person's line) and turns without the header (Hermes, jobs) are unchanged; the play screen follows the stream (EventSource) instead of polling the draft; measured on the route (n = 2, `docs/measurements/rpg-latency-route-stream-2026-10-25-n2.json`): outcome visible 0.14-0.20 s for look, arrive, buy, fight and wait (was 8-21 s), a person's line 3.5 s (written before the commit), first narration 7-11 s; open: a durable job for a narration a crash cut off, the map's poll, Hermes waiting on `narration.final`, several replicas (the event log), the line after the commit, first narration (RQ-6.5) |
| RQ-6.5 part 1 | the writer's payload sends each evidence once | 8cf825a6a7 | the narrative writer's request carried every evidence record three times (in its beat, `approved_evidence`, `evidence_by_beat`) with its bookkeeping (revision, confidence, lifetime, metadata): now once, in its beat, as the writer reads it; a look in Aurelia 18.6 KB -> 5.0 KB, an arrival 8.0 KB -> 4.7 KB; on the route (n = 2) no measurable change: a person's line takes about 3 s (the CLI's start), narration 10-20 s, growing with what it writes (the blocks and their claims), and the narration check asked for a rewrite in some turns; open: the writer's output (claims) and the provider, a world-canon prefix for providers that cache prompts |
| RQ-6.4 part 1 | the turn's hot spots | a65507c9a1 | profiled (`submit_rpg_turn`, a look in Aurelia): each campaign load built and hashed all 38 map definitions (twice a turn), evidence was scored four times per record, every reduce deep-copied the document, and the scene lore read and projected the published world's canon twice; now the map repository is kept per world graph, each record is scored once, the reducer copies by pickle (`copy_state`), and a published revision's projected canon is kept; the overhead rehearsal (50 turns): p95 373 -> 274 ms at 100 KB, 450 -> 333 ms at 1 MB, 56 -> 54 statements; open for F2 (150 ms, 20 statements): the commit rewrites the whole document each turn (105 ms and 180 KB of WAL at 1 MB), the statements, the scene lore's projection saved each turn |
| RQ-6.4 part 2 | one load fewer, one insert fewer | 1c722b66ea | the TurnOutcome's turn-start document is the one the pipeline loads (`turn/run.py` `keeping_turn_start`), not a second read of the campaign; a narrative response the turn's unit of work inserted is not saved again when its delivery opens; 54 -> 50 statements, p95 at 1 MB 333 -> 321 ms; the statements left: the foreground job mirror (about 13: the job, its events and logs, for Developer tools), the campaign bible read three times, the load inside the commit |
| RQ-8.4 | the operations view | 8c3d59edbb | migration 0184 `omnix_rpg_turn_metrics` (row-level security, kept 90 days by the retention job): a row per turn the route ran, written beside the turn and never failing it: its class (the planned mechanic, else the turn's kind), failed or not and how (a game refusal, a 4xx, is no failure), degraded stages, time, model calls and model failures; a narration that fails after its commit is a `narration` failure; `GET /api/rpg/operations?days=` gives each day's failure and degraded rates, latency per turn class (p50, p95) and model calls a turn (the provider reports no token cost, so calls are its measure); Developer tools shows it (`RpgOperationsPanel`, in `RpgDeveloperTools`, which also moves the Hermes panels out of `RpgWorkspace`); the turn stream's isolation between users is tested with RQ-8.3 (414a267800) |
| RQ-3.3 part 3 | the person addressed answers, again | e206d2be61 | the real-model pilot (n = 60) fell to correct speaker 0.348 (0.675 at part 1): "what would happen if I attacked Liora Fen?" was read by the intent call as an attack, and the fight it began answered every later remark with "You are in a fight" (near-duplicate 0.32); a hypothetical (what if, what would happen if, suppose) is now a question, never the deed, in the grammar and over the model's readings, asked of the person it names, and with no one named the one person here answers; speaking to someone the world knows who is away says so, and where their day has them, with no time passing; a person's names include what they do ("the captain", "my guide") and their name without its title, and the intent call sees each person's other names; the pilot reads who is present from the campaign (the corpus's static scenes expected people their routines had moved) and counts those turns apart; after: correct speaker 0.909 (n = 33; Aurelia 0.94, starter 0.91, Vesper-9 0.83), near-duplicate 0.10, contradictions, leaks and failures 0 (`docs/measurements/rpg-narration-pilot-2026-10-25.json`); held-out grammar unchanged (family 0.988, target 0.992) |
| (RQ-7.7 find) | an opening's derived places are named after their place | 2dcb44b94b | Vesper-9's opening offered a road to "Starter": the starter bubble's slots were named by their id's last word; the bubble's region is no place itself, and its interior, outskirts and frontier are named after their place ("Black Rain Station Interior") |
| RQ-7.6 | landmarks, the page's heading, a story log the keyboard reaches | e6b60099ea | axe on the live play screen at 1,440 x 900 and 360 x 740: no `<main>` inside the shell's (the centre stage is a labelled section), the scene's place is the `h1`, the story log takes focus; 0 serious or critical issues, no sideways scroll at 360 px |
| RQ-7.7 part 1 | the core tasks in a real browser; undo, save points and coming back on the play screen | 2e3d995a15 | `scripts/rpg_core_tasks.py`: a fresh Aurelia campaign per viewport (360 x 740, 1,440 x 900), each task driven on the play screen and checked against the campaign itself; 10 of 11 pass at both sizes, axe 0 serious or critical, no sideways scroll; the grid fight waits on its foe being on the map (RQ-7.7 part 2). Built for it: Undo beside Submit and the Campaign Menu's save points (name, return, delete: `/rewind`, `/save-points`), each a turn in the story log; coming back after 10 minutes away (opening the campaign, or the tab shown again) runs the resume turn; the item panel offers what the item rules allow (`items.pack_actions`, on the player view: use, equip or unequip, drop, sell) and shows the world's description, with no model call; Sell is a sell turn. Found and fixed: a campaign's list time was its creation (the row's `updated_at` is when it was last played, and Continue now opens the latest played); a pack action left the play screen's cached campaign stale; "Lantern Bread" could be held to hand; the pack listed 8 things at most; Save Game wrote a platform checkpoint, not a save point, and the New Game setup and Settings views were unreachable or changed nothing (deleted with the older item calls: item details by model, diagnostics, the merchant menu); 0184's retention row moved to platform migration 0185 (AL016) |
| RQ-7.7 part 2 | the fight on the local map; creatures met where they live | 5a514b8cda | `scripts/rpg_core_tasks.py`: all 11 tasks pass at 360 x 740 and 1,440 x 900 (`docs/measurements/rpg-core-tasks-2026-10-25.json`), axe 0 serious or critical, no sideways scroll. The local map follows the hero (`LocalMapEntered`; a place's instance made on the first visit, in the turn's transaction); a fight's foes stand on it, beside the hero when the fight begins and closing in when they act, kept in the fight's own state (rewind and replay cover it), seen by the grid's view, moves and attacks (`foes_on_grid`), named by the fight (`actor_names`; a wolf showed as "1"). Found and fixed: the play screen's grid stayed the opening's after any journey; any creature could be fought anywhere (a wolf in the guild hall): a creature is met in the wild or where a quest sends the hero for it (encounters.md). Playthroughs, balance simulation (bands hold), latency harness and the Aurelia golden (re-recorded: a Glass Wight bars Skybridge Pass) meet creatures in the wild |
| RQ-7.1 part 2 | the play screen speaks to players | 0ab99ed765 | the fight panel reads the fight as the campaign holds it (`rpgCombatState.buildRpgFight`: turn order, each one's real health and conditions, whose turn) and shows only in a fight; it invented foe names from a text line, health ("HP unknown") and an initiative order, and offered two moves no rule plays (Rally party, Inspect enemy); its moves are the composer's suggestions. The rail's encounter card, the scene line "Live replay-persistence session indexed by the backend" (now the scene's own description), the journal's session id and checkpoint lines, "Renown Unknown (0)" (a constant no rule moves), "Not tracked yet" world rows and the story tabs' replay wording are gone or say what they mean; the jobs/autoplay card and turn diagnostics (shown on every localhost page, which is every Omnix page) sit behind Developer tools. Narration: a fight turn told its outcome three times ("Consequence: …", "Offered choice: …"): the deterministic writer tells each evidence sentence once, the consequence beat (which cites the action's own facts) is optional, and the repairer leaves out an optional beat that only repeats another (goldens re-recorded: narration only, no fact changed). 11 of 11 core tasks still pass at both sizes. |
| RQ-7.1 part 3 | the journal is the hero's own account | af096e2d26 | the pipeline passed its outcome lines where the journal never read them (`turn_contract.summary`), so a day's entry strung the typed commands together after a stock opener ("I tried to read the day clearly... go to Starfall Village."); it now tells the game's own lines in the hero's first person ("I hit the Echo Wolf... The Echo Wolf hits me..."), the opener only when the hero's voice gives one; golden re-recorded (document hash only) |
| RQ-2.10 (items) | the older item path, deleted | 1bbb97bd78 | the compatibility route's item actions (item action, command, detail by model, resolve, diagnostics, maintenance, objectives, scenarios) and its loadout action had no caller once the item panel offered the item rules' own actions (RQ-7.7): removed, with the web's loadout fallback (a 404 for a missing campaign fell back to an unrelated payload); reachability then removed 13 modules and the unreachable names of the item modules they kept alive (save-outside-the-turn writes among them: AL019 baseline shrunk); the ability tooltip's detail stays |
| RQ-7.5 part 1 | no play-screen file over 600 lines | 3e70986cd1 | `rpgUiState.ts` (1,299) is its types (`rpgUiTypes`), preview fixtures (`rpgUiPreview`), record readers (`rpgUiRecords`), story and journal (`rpgStoryState`) and the workspace state (543); `RpgLoadoutTabs.tsx` (1,118) is the tabs (150), their panels (`RpgLoadoutPanels`) and the ability overview (`rpgAbilityOverview`); `RpgWorkspace.tsx` (963) moved its helpers (`rpgWorkspaceSupport`), live-data cards (`rpgLiveDataCards`, four copies of one state ladder made one) and Hermes's assist (`useRpgHermesAssist`) out (580; its function ratchet 713 -> 534); `RpgCampaignCharacterStep.tsx` (712) its creation-progress parts; `RpgActionComposer` was split in RQ-7.7 (its ratchet entry deleted). A declaration file that augmented a type now living elsewhere is folded into the type. Scorecard: RPG web files over 600 lines 4 -> 0. Also: the outcome card's gain and loss colours follow the appearance (the appearance contract). Not yet: one stylesheet per component, the light/dark screenshots |
| RQ-7.5 part 2 | one stylesheet per component; the play screen in light and dark | 61c3706f08 | `RpgWorkspace.css` (1,437) and `RpgResponsivePolish.css` (389) were the play screen's styles for every component: each rule now lives with the one component that names its classes (`RpgStoryScene.css`, `RpgActionComposer.css`, `RpgPlayerRail.css`, `RpgWorldRail.css`, `RpgWorkspaceHeader.css`, `RpgLoadoutPanels.css`, `RpgLorePanel.css`, `RpgLiveDataStatus.css`, `HermesSequencePreview.css`, each imported by its component). What several share is split by the cascade it relied on: a shared rule a component's own rule overrode loads before the components (`RpgWorkspaceBase.css`), the rest (the layout) after them (`RpgWorkspace.css`, 567 lines); repeated selectors within a sheet are one rule. The world editor's lifecycle badge shared a class with the world rail's state card (`.rpg-world-state`: hidden under 1,180 px, its font leaking into the rail) and is now `.rpg-world-lifecycle`; a combatant card's name and side sit on one line again. `scripts/rpg_play_screenshots.py` captures the play screen at 360, 768 and 1,440 px in light and dark without moving the campaign on (no resume after time away) and compares two sets pixel by pixel: the split leaves every image the same but 1 px taller (the combat panel's own gap now applies), merging the repeats changes no pixel, and two captures in a row are identical (`docs/measurements/rpg-play-screens-2026-10-25.json`). Core tasks after the split: 11/11 at both sizes. |
| RQ-4.1 | an author writes how a world plays, and the next campaign plays it | da7b0d66d0 (review fixes d87ad49e41) | the world editor's How It Plays page (`RpgWorldPlaySectionsPanel`, Game Master): the economy, routines, knowledge, pressures and bestiary as forms over the world's own people, places, items, creatures, regions and quests; the draft is kept with the world (metadata `play_sections`, a save names the draft it replaces: 409 on a newer one, 422 naming each error) and published through the library's publications, which write it into the revision's canon after the authored blueprints (`play_section_publication`) and refuse one naming what the world lacks. World Forge drafts empty sections from the lore (`play_section_generation`, deterministic, no model: sellers by role at the world's prices with only its own items, each person's place and goals, public truths told freely and secrets when trusted, the world's pressure entities eased by the quests naming them plus road dangers, creature numbers by threat). Launch readiness: each section `authored` or `derived` per revision (world detail, the editor's tabs, the campaign setup's "How it plays"). Found: release validation read people, items, quests and regions only from authored canon sections, so a lore world (Vesper-9) could never validate an authored section (`lore_rows` gains items and quests, used by validation, authored goods and launch's derived goods); a world written by hand or installed from a bundle (Aurelia) had no way to republish (the repair needed a generation run or imported topics): it is republished as its latest revision stands, its map definitions issued again for the new revision; a repair reused a promotion without the latest sections (it now matches their hash); the prompt registry still listed the deleted item-detail module. Tests: 7 unit, route (409/422), PostgreSQL end to end (Aurelia: draft from lore, save, conflict, wrong shape, unknown person refused at publication, publish, the pinned revision plays the authored price), web 3; browser: Vesper-9 drafted, saved and published from the page (3 s), axe 0 and no overflow at 1,440 and 360 in light and dark. Open: model-written sections (the draft is the lore's inference) |
| F2 part 1 (RQ-6.4) | a turn without its job mirror, its lore pass when nothing changed, its lock's connect, and a document that stops growing | 6ada147053 | the gate (`turn_overhead`, 200 turns per size; `docs/measurements/rpg-turn-overhead-2026-10-25.json`): p95 296 -> 157 ms at 100 KB and 352 -> 198 ms at 1 MB, statements 44 -> 20 (p50; p95 22), world-tick catch-up p95 117 ms (budget 500). What changed: a foreground turn wrote a second, record-only job beside its submission claim (insert, claim, three events, four log reads, completion: a third of its statements) that nothing read; the claim already makes a turn exactly once, and the commit completes it in the turn's transaction (`session/jobs/foreground_turn.py`, the claim carried in `foreground_context`). The scene-lore pass (two bible reads, the world canon merged twice, a materialization: about 75 ms on a scene turn) ran though the bible already covered the scene: a per-process memory of what each bible covers, checked against its stored hash and the world it is bound to, grounds the turn from it (`runtime_lore_store._COVERED`). The turn-order lock opened a connection each turn (about 15 ms): its connections are kept (`turn_order`). The commit no longer reads back what it knows: the delivery record it opened, the response a delivery and a retirement name (checked in their inserts), a turn of a submission it holds open, the maps of a turn that touched none. A campaign grew a kilobyte a turn (1,000 turns: 1.2 MB): the causal world runtime kept every event at about 4.5 KB each, now the last 12 with its initial state rolled forward so they still replay; the calendar's history is a day's 24 entries and the world's events 64; growth is now about 200 bytes a turn and levels off. Found in review: a memory hit returned names where grounding needs the canon ids ("liora fen", not `npc:liora_fen`). Open for F2: the commit still writes the whole document (about 65 ms at 1 MB, most of the 1 MB gap: lz4 compression did not change it), so the 1 MB budget needs the document stored in parts; 100 KB p95 is 7 ms over and statements p95 2 over |
| RQ-8.6 | a campaign carried to another Omnix | ab075d028a | Load Game saves a campaign to a file (`GET /api/rpg/sessions/{id}/export`: a save package, format 8, whose `transfer` section carries what the document plays from: its creation artifacts and bible, its world binding, its local maps and its narrative responses) and imports one (`POST /api/rpg/sessions/import`, `session/persistence/campaign_transfer.py`): everything written in one transaction under the campaign's own id (`save_session_to_postgres` writes inside a caller's unit of work); refused, with what to do, when the campaign is already in the library (its ids run through its document), when its world is not installed (import the world first), and as before for a newer document (503); the turns' history before the export stays behind, the campaign arriving at its revision as its first snapshot. PostgreSQL: an Aurelia campaign played, exported, taken out, imported and played on, its narrations and local map with it; web: saved to a file, and imported into an empty library |
| RQ-2.8 slice 6 | the engine has no world of its own (A4: AL021 at 0) | f184f06c33 | the starter town's last copies in engine code are gone, the bundle (slice 1) being their one source: the location registry and the travel graph read only the campaign's world model (no built-in places or roads; a state without a world names no place); a biography is the world's person (`world_model.npcs` and the session's index, read through `foundation/state/people.py`), or a plain one that claims nothing (the Bran/Mira/Merchant/GuardCaptain table, its aliases and the file profiles are deleted); the schedules and goals seeded into every campaign, the conversation fallbacks (`npc:Bran`, `npc:Mira`, tavern and market topics and lines), the fixture visual maps (`map_fixtures`, `map_hierarchy_fixtures`; a campaign's maps are its world's), the starter climates, the scripted cloaked-traveler fallback narration and the narrators' Bran lines are deleted, and a new game's base before the opening holds only the player's choices (hook, pace, relationship) by key; the narrative engine's handcrafted evidence moved to the tests; found: a topic named its place by id (the location lookup had no state), lore projection titled an item met as a person by its raw id (`healing_potion`), the published-world golden had not been re-recorded after F2's event cap, and the recorded turn path still named the deleted `turn_job_mirror` (now `foreground_turn`); open: process-local state the roadmap added is unreviewed in the register (`turn_stream`, the lore store's memo, world sharing, narration drafts, the turn-order idle pool, map repositories) |
| RQ-9.1 | a player plays the reference worlds for hundreds of turns | 9c07c13dbb | `scripts/rpg_autoplay.py`: a seeded policy player (rest when hurt, eat when hungry, talk, ask about work and wares, travel, fight in the wild) or a model player (`--player route`: Claude Haiku through the CLI, the policy standing in when it gives no usable line) plays Aurelia, Vesper-9 and the starter world through the turn route on a disposable database, and after every turn checks the invariants (health in bounds, no negative purse, no stack below one, the revision never back, no unknown place), a visible line for every accepted turn, server errors and refusal streaks; the report (`docs/measurements/rpg-autoplay-2026-10-25-policy-scripted.json`) has latency overall, by action and over the first and last hundred turns; 500 turns per world, scripted model: all pass, no findings, refusals 0, places 4/9/6, no drift (p50 first/last hundred: Aurelia 107/105 ms, Vesper-9 201/180, starter 94/108); found: Vesper-9's dialogue costs about 560 ms (ask, talk; everything else 170-220 ms), its turn grounding re-merging and re-hashing a large bible each turn (the encountered-NPC sync and the turn snapshot: 0.55 of 0.74 s profiled), an F2 item, where a memo needs the projection's hash to cover its discovery state (a page marked read leaves the hash as it was); the policy player finishes no quests (it never takes a job): quest play is the model player's run, open |
| RQ-2.4 part 3 | the loadout is turns; one ability system (A2: AL018 at 0) | 14f3b52f0b | every loadout action is a structured-action turn through the pipeline: a pack action (as before), an ability used (`rules/ability_use`, in a fight or not: out of one it is paid for and begins its cooldown, its heal heals, what it restores of the hero's own stamina or mana comes back, the rest the story tells, a striking one needs a foe; "use Trail Sense" in the player's words plans it too), one learned (a level's choice, `progression.choose`, so only while one waits), and a hotbar slot set or cleared (`HotbarChanged`, the vocabulary's 51st change; no time, no journal entry); the turn route saves nothing after a commit, and the deferred narration job reports its interaction's outcome without saving the campaign (07c4891ed8); deleted: the second ability system (ability points, Upgrade and ranks nothing read, its effect-op engine writing state only the deleted turn path read, a cooldown counter the reducer overwrote), the world-scale abilities injected into every hero's tree (naming the starter town's factions), and the loadout's crafting, salvage, modifications and inspect, which had no world catalog and no caller on the play screen: 30 modules and some dead names, about 5,700 lines, with the tests of only them; the play screen's ability tree shows the level's choices waiting and offers Learn; its skill threshold is the pipeline's curve (50 x (rank + 1)); AL018 3 -> 0 |
| RQ-0.7 refresh | the turn path re-recorded after RQ-2 | cd23eb6ebe | `scripts/rpg_turn_path.py --write` over the playthrough suite and the published-world golden: 196 modules (was 298; 157 off it since the older path went, 55 measured on it for the first time: the pipeline's rules and turn stages); every state-changing request now enters through the turn route, so it is the one entry point measured (the loadout and the tactical routes' own hooks named functions that no longer exist); the ratchets follow the measured set: AL019 377 -> 181, AL020 248 -> 311, the rise being the newly measured modules' existing reads (168), with no module already on the path above its count; `docs/measurements/rpg-unexecuted-modules-2026-10-25.json`: 171 RPG modules no scenario imports, 288 imported with no function run |
| RQ-1.5 (AL020) | a section's key named once (AL020 at 0) | c85a879af1 | `foundation/state/access.py`: an accessor per section key the lint watches (the document's simulation and runtime state; the simulation's hero, world model, people, presence, quests, fights, survival, economy and travel; the hero's pack and party), each returning what its holder keeps as it keeps it (the same object, or `None`), so `holder.get("player_state")` became `player_state_of(holder)` with nothing else changed: 311 reads in 69 modules by a codemod (one-argument `.get` only), two by hand (a `.get` with a default, a subscript of a holder built two lines up); this names where each section lives in one place, it does not type the sections (that is `sections.py`'s view, which the rules read where they were written for it); a test ties the accessors to the lint's keys |
| RQ-1.5 (AL019 owners) | the document's upgrade is the reducer's one fellow writer | 698005eace | AL019's owners name, besides the reducer (`foundation.state`), the document's upgrade: `session.campaign_state`'s upcasters and the interaction-timeline migration they run reshape an older version's document once, outside any turn, as a system turn with a pinned backup (operator-notes.md), the way AL018's owners name persistence and the commit; they cannot live in `foundation` (an upcaster binds old campaigns to the starter world, a `genesis` module); AL019 181 -> 157 |
| RQ-1.5 (AL019, bookkeeping) | the campaign's bookkeeping is the reducer's | 722eefd68b | a 14th section, `interactions` (the interaction timeline, the sequence and state revision, the recent and last interactions, each interaction's lifecycle), typed in the view, and four changes the commit's bookkeeping now goes through: `InteractionRecorded` (the commit's append), `LifecycleRecorded`, `InteractionPresented` (the narrative engine's projection on the recent interaction) and `InteractionsReplayed` (the event log merged in on load); the modules compute the records, the reducer writes them; `reduce(..., owned=True)` applies in place for a caller that holds its own copy (the commit, the loader), so the bookkeeping costs no deep copy (overhead unchanged: p95 154 ms at 100 KB, 206 at 1 MB); found: a rewind restores the game's runtime sections, so it now leaves the new section, the campaign's bookkeeping, as it is (an earlier sequence reused an interaction id); the vocabulary has 55 changes; AL019 157 -> 136 |
| RQ-1.5 (AL019, rules) | the rules write no state they are handed | d89693f2ae | the fight's turn order is pure (`runtime_turns.next_turn`: the section in, the advanced copy out; the fight rule took it through a throwaway holder); the older stakes functions the fight and rest rules replaced (defeat, attack penalty, rests, wounds) are deleted with their unit tests (the playthroughs cover the same outcomes on the pipeline), and so are the combat core's hero and HP-sync writers only they called; healing reads the party without creating a hero section; the survival and progression normalizers, already pure, name their fresh copy for what it is; found: a pass that took reachability from production code alone flagged 311 names, and deleting 103 of them broke 22 playthroughs (prompt modules the registry names must keep their templates; dialogue routing): reverted, and the dead-code pass keeps the tests as roots; AL019 136 -> 103 |
| RQ-1.5 (AL019, version 9) | what every load added when missing is added once | 862c73d169 | document version 9: its upcaster gives an older document, once, the environment's seed state and a published opening's quest and first actions, which every load used to add when they were missing (and would have added the opening quest back to a campaign whose quest list was ever emptied); a current document loads as stored; the upgrade's code lives in `session/upgrades` (the interaction-timeline migration, the opening's progress, the environment seed, moved out of `world/environment.py`), which AL019's owners now name as the document's upgrade; the causal projection and the lore store's hydration name the working copy they write (the causal tick's, and the hydrated session); the golden's documents differ only in `manifest.schema_version`; AL019 103 -> 80 |
| RQ-0.7 fix | the turn path counts calls, not imports | 35e08124ba | `scripts/rpg_turn_path.py` counted every profile "call", and a module's top level run by an import the turn makes is one: modules only imported during a turn were on the turn path (the older idle, ambient, companion, NPC-reaction, conversation-thread and normalizing modules, none of whose functions a playthrough runs); it now counts function code only (`CO_OPTIMIZED`), as its definition says, with a test; 174 modules (24 off); the older travel graph's route listing, destination resolution and state update, which the pipeline's travel replaced, are deleted with their tests; the process-local register reviews the turn stream, the narration drafts and the turn lock's idle connections; AL019 80 -> 47, every remaining write in a module whose functions a turn calls |
| RQ-1.5 (AL019, load and save) | a turn's load reads the campaign as stored | 951ea53d06 | measured over the playthroughs (1,604 saves, 618 turn loads): the save's ambient normalization never changed a document and its ambient defaults only added an empty list every reader defaults itself, so both are gone from the save; the hero's simulation record, filled from the sheet on every turn's load (130 times, each a campaign's first turn), is filled once instead, when the campaign is created (`new_game._save_created_session`), imported, or upgraded to version 9 (`upgrades/hero_record.py`), with the hero's progression defaults; the published-world golden's opening document is now the hydrated one, and its first nine turns' sheet items carry the store's `category` and `item_id`; open: the map state, which the save integrates from where the hero stands (428 of 1,604 saves), is next |
| RQ-1.5 (AL019, map state) | the world map follows the hero within the turn | cb217ebba9 | the play screen's world map state was projected from where the hero stands by the save's normalization, which the turn's commit does not run: a travel turn stored the previous place's map until some later non-turn save; the projection is pure now (`map_world_integration.projected_map_state`) and a change, `MapStateProjected` (the 56th), which the turn adds after its own when the map differs, and a campaign's creation once; the save no longer touches it, and `world/map_persistence.py` is deleted; the turn's patch records `state/map_state` and the outcome names the location among its changed domains on a travel turn (both goldens re-recorded for that) |
| RQ-1.5 done | A2's ratchets at 0: AL018, AL019, AL020 (and A4's AL021) | b3aadfdd73 | the turn path re-recorded after the load and save no longer reshape a campaign: 170 modules (the hero bridge, the ambient builder and the progression normalizer are off it); the journal step is pure (a new calendar and journal out, the turn's runtime only read); the causal tick's runtime and event log name the working copy they write, which the tick hands the reducer as `WorldTicked`; AL019's owners name, besides the reducer and the document's upgrade, the save (AL018's owners), which keeps the stored record: the immutable seed, the revision an edit outside a turn takes, the manifest; AL019 47 -> 0 |
| process-local state | every RPG process-local value reviewed and bounded | (this commit) | the register named none of the state the roadmap added: the turn stream and the narration drafts (coordination: a turn's events for this replica's subscribers, already bounded and expiring), the turn lock's idle connections (per-connection), the lore store's two memos and the map repositories (caches: each now expires after an hour and has a clear function, `clear_lore_memos`, `clear_map_repositories`), the built-in worlds' source, bundle and revision (unbounded `functools` caches, now the bounded, expiring cache), and the sharing page's GitHub sign-ins (expired ones are forgotten when another starts, 32 at most: they were kept until polled again); `PROCESS_LOCAL_STATE.md` regenerated; the 13 entries still unreviewed are other features' (trading, voice, the speech services) |
