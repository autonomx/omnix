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

A registry test lists each owner and fails when a second module writes the same state section.

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
| RQ-0.9 | done (scratch); operator run pending owner permission | 44bb59d9e9 | `scripts/rpg_replay_audit.py`; 4 tests pass; scratch audit in `docs/measurements/rpg-replay-audit-scratch-2026-10-23.json`: no snapshot at creation (turns 1–19 unverifiable), new campaigns 1.7 MB from duplicated bootstrap/genesis snapshots |
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
| RQ-1.4 slice 4 | early answers are turns | (this commit) | an unclear command is planned as `clarify`: a counted turn in which no time passes, its question published as the turn's canonical prose with no model call (`OMNIX_RPG_TURN_PIPELINE_CLARIFY`); the RQ-3.1 ambiguity scenario now expects a committed turn |
