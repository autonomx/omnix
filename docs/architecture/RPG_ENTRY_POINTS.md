# RPG entry points (RQ-0.8)

Status: inventory of 2026-10-23, at `a6034e01bd` (branch `rq-b`). Input to RQ-1 (one turn pipeline, roadmap §4.1).

This lists every mutating RPG HTTP route (POST, PUT, PATCH and DELETE under the RPG feature routers, the
compatibility router and the Hermes routers) and every RPG job kind, with what each writes, the concurrency token it
relies on, and the turn kind it becomes under §4.1 (`player_text`, `structured_action`, `world_tick`, `system`) or the
exemption that keeps it outside the pipeline, with the reason.

`src/tests/rpg/test_rpg_entry_points_inventory.py` builds the routers and fails when a mutating route is registered
that this file does not list, or when this file lists a route that no longer exists. A new mutating route therefore
needs a row here, with a turn kind or an exemption.

## Terms

- **Campaign document**: `omnix_rpg_campaigns.state_jsonb` (the session: `state`, `simulation_state`,
  `runtime_state`, manifest), hashed into `state_hash`.
- **Out-of-turn save**: `save_session` / `save_runtime_session` outside a turn. Under PostgreSQL the save is an
  optimistic `UPDATE ... WHERE revision = <loaded revision>`; when the loaded revision equals the stored one and the
  hash differs, the save becomes the next revision (`session_records.py:121-142`). It writes no turn row and no
  patch. The token is the revision the handler loaded, not one the client sent, so two such saves from stale reads
  conflict only if they interleave inside the same load-save window.
- **World tables**: `omnix_rpg_world_*` and `omnix_rpg_scenario_*` (projects, drafts, topics, revisions, releases,
  generation runs, images, map blueprints). They hold authored worlds, not a campaign.
- **Exemptions** follow §4.1: persistence modules, campaign creation, import, adoption and admin routes may write
  outside the pipeline. This file adds three more reasons, each to be confirmed when RQ-1 lands: *read-only* (a POST
  that only reads or computes), *world authoring* (writes world tables, never a campaign), and *narration transport*
  (delivery cursors, which §4.1 step 10 keeps outside the campaign).

## Turns and play actions

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/rpg/sessions/{session_id}/turn` | `edge/api/feature_routes/rpg_session_routes.py` → `edge/api/turn_pipeline.py` | Under PostgreSQL the whole turn commits atomically in `persist_foreground_turn`: campaign document and revision, turn row and patch, interaction, canon, queued jobs, submission, canonical narrative response. Early returns in `player_turn_execution` still save directly (§3). | Submission row `FOR UPDATE` and campaign row lock at commit; optimistic campaign revision (`RevisionConflict` → 409); `x-omnix-rpg-submission-id` is the idempotency key | `player_text` |
| `POST /api/rpg/sessions/{session_id}/loadout-action` | `session/loadout.py` (`apply_loadout_action`) | Campaign document (equipment, hotbar, abilities, ability coverage snapshot) by out-of-turn `save_session` | Loaded revision only; the client sends no token | `structured_action` |
| `POST /api/rpg/sessions/{session_id}/maps/{map_id}/map-actions` | `edge/api/feature_routes/rpg_map_routes.py`, `world/map_actions.py` | Campaign document (map overlay state, overlay revision) by out-of-turn `save_session` | Client sends `definition_revision` and `overlay_revision` (409 when stale); campaign save on the loaded revision | `structured_action` |
| `POST /api/rpg/map-instances/{map_instance_id}/tactical/move` | `world/tactical_spatial_service.py` (`move_actor_tactically`) | `work.rpg.commit_turn`: campaign revision and turn row (`tactical-spatial-v1`), map-instance snapshot and map event | `expected_campaign_revision` and `expected_map_state_revision`; map instance row lock; idempotent by command id | `structured_action` |
| `POST /api/rpg/map-instances/{map_instance_id}/tactical/attack` | `world/tactical_spatial_service.py` (`attack_tactically`) | As tactical move, plus the attack's combat result | `expected_campaign_revision` and `expected_map_state_revision` | `structured_action` |
| `POST /api/rpg/map-instances/{map_instance_id}/geometry-patches` | `world/map_geometry_patch_service.py` | Map-instance snapshot and a map event (`omnix_rpg_campaign_map_instances`, `_map_events`); no campaign revision | Map instance row `FOR UPDATE`; command's `expected_map_state_revision`; `command_id` | `structured_action` (its map change must commit with a campaign revision so `maps_hash_after` covers it) |
| `POST /api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/observe` | `world/map_observer_service.py` | Observer knowledge rows (RPG migration 0028): what an actor has seen of the map | `expected_knowledge_revision`, optional | `structured_action` until each turn's commit records what the player saw; then read-only |
| `POST /api/rpg/sessions/{session_id}/resume` | `edge/api/feature_routes/rpg_session_routes.py` → `edge/api/turn_pipeline.py` → `session/turn/run.py` (`run_world_tick_turn`) | The turn route's unit of work: the world_tick turn's document (clock and causal sections), turn row and patch, submission, its recap as the canonical response (RQ-2.7) | As the turn route: one turn of the campaign at a time, `x-omnix-rpg-submission-id` | `world_tick` |
| `POST /api/rpg/sessions/{session_id}/continue` | `session/new_game.py` (`continue_rpg_session`) | Today only loads. `load_session` replays interaction events and may recover pending interaction narration, which can save runtime state | None | `world_tick` (the resume catch-up of §4.5; today no route runs it, see "Not reachable" below) |
| `POST /api/rpg/campaigns/{campaign_id}/spatial-ticks` | `world/npc_spatial_campaign_runtime.py` (`advance_campaign_spatial_tick`) | `omnix_rpg_campaign_spatial_clocks`, `omnix_rpg_npc_spatial_goals`, `_routines`, `_transitions`, `_tick_runs`, and map-instance snapshots for moved NPCs (RPG migration 0027); none in the hashed document | Campaign row lock; `expected_world_tick` | `world_tick` |
| `POST /api/rpg/campaigns/{campaign_id}/spatial-goals` | `world/npc_spatial_campaign_authoring.py` | `omnix_rpg_npc_spatial_goals` | `expected_revision` (default 0 = create) | Exemption, admin: authoring a campaign NPC's goal. Retires with the spatial runtime's mutable tables (§4.3 NPC routines); authored goals move to the world revision |
| `POST /api/rpg/campaigns/{campaign_id}/spatial-routines` | `world/npc_spatial_campaign_authoring.py` | `omnix_rpg_npc_spatial_routines` | `expected_revision` | Exemption, admin, as spatial goals |
| `POST /api/rpg/campaigns/{campaign_id}/spatial-policy` | `world/npc_spatial_campaign_authoring.py` | `omnix_rpg_campaign_spatial_clocks` (tick policy) | Clock row `FOR UPDATE`; `expected_world_tick` | Exemption, admin, as spatial goals |
| `POST /api/rpg/sessions/{session_id}/lore/discovery` | `edge/api/feature_routes/rpg_campaign_lore_routes.py`, `genesis/forge/campaign_lore_store.py` | `omnix_rpg_campaign_bibles` (a lore document's discovery state, new canon revision), then the portable projection into the campaign document by `save_session` (errors swallowed) | Campaign and bible rows `FOR UPDATE`; bible `expected_revision`; campaign save on the loaded revision | `structured_action` (the player marks lore discovered) |
| `POST /api/rpg/sessions/{session_id}/lore/regenerate` | `genesis/forge/campaign_lore_store.py` (`regenerate_campaign_lore_document`) | Model call, then `omnix_rpg_campaign_bibles` (new canon revision) and the campaign projection save | Bible `expected_revision` | Exemption, canon authoring (a model rewrite of one page). Must stop saving the campaign projection (RQ-1.4) |
| `POST /api/rpg/sessions/{session_id}/lore/materialize` | `genesis/forge/runtime_materialization.py` (`materialize_runtime_lore`) | Model call, then `omnix_rpg_campaign_bibles` (runtime definition, new canon revision) and the campaign projection save | Re-reads the source revision under lock; bible `expected_revision` | Exemption, canon authoring, as regenerate |
| `POST /api/rpg/narrative-responses/{response_id}/cancel` | `edge/api/feature_routes/rpg_narrative_delivery_routes.py`, `narration/narrative_engine/delivery.py` | `omnix_rpg_narrative_deliveries` (cursor cancelled before publication) | The response's `semantic_hash` | Exemption, narration transport |
| `POST /api/rpg/sessions/{session_id}/rename` | `session/new_game.py` (`rename_rpg_session`) | Campaign document (manifest and state title) by out-of-turn `save_session` | Loaded revision | Exemption, admin (title). Should write the title column without a document revision |
| `POST /api/rpg/sessions/{session_id}/delete` | `session/persistence/session_records.py` (`archive_session_in_postgres`) | `omnix_rpg_campaigns.status = 'archived'`, `revision + 1`, `manifest.archived` set in the document by SQL | None (unconditional `UPDATE`) | Exemption, admin (archive). Should not bump the document revision |

## Campaign creation and binding

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/rpg/new-game` | `session/new_game.py`, `genesis/forge/async_coordinator.py` | New campaign (campaign row, participant, document), campaign genesis job when generated | New ids | Exemption, campaign creation |
| `POST /api/rpg/presets/{preset_id}/start` | `session/new_game.py` (`start_rpg_preset`) | New demo campaign (Glimmerdeep) | New id | Exemption, campaign creation |
| `POST /api/rpg/scenarios/{scenario_id}/revisions/{scenario_revision}/launch` | `genesis/worlds/published_launch.py` | New campaign launched from a published world: campaign row and document, world binding, campaign bible, map instances | New id; pinned world and scenario revisions | Exemption, campaign creation |
| `POST /api/rpg/local-qualification/dialogue-fixture` | `edge/local_dialogue_quality_fixtures.py` | A benchmark campaign document (`save_session`) | Local requests only (`_require_local_dialogue_fixture_request`) | Exemption, test fixture (local qualification only) |
| `POST /api/rpg/campaigns/{campaign_id}/world-binding` | `genesis/worlds/postgres_service.py` (`bind_campaign_world`) | The campaign's world binding row (world, revision, release, scenario) | Pinned revisions; authorship checks | Exemption, adoption (binds a campaign to a world). RQ-2.8 binds unbound campaigns in the upcast |
| `POST /api/rpg/campaigns/{campaign_id}/legacy-world-import` | `genesis/worlds/legacy_bible_import.py` | World tables (a world and scenario compiled from the campaign's bible); the campaign is not changed or rebound | Reads the bible revision | Exemption, import |
| `POST /api/rpg/campaigns/{campaign_id}/materialization-signals` | `genesis/worlds/progressive_materialization_job_service.py` | Enqueues `rpg.world.map.materialize` jobs for the campaign's world | `create_job_once` | Exemption, world authoring (a world job; no campaign write) |

## World authoring, library and sharing

All of these write world tables or the world library and sharing state, never a campaign document. Exemption for each:
**world authoring** (or library and sharing), unless noted.

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/rpg/worlds` | `edge/api/feature_routes/rpg_world_routes.py` | New world project | New id | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/archive` | `rpg_world_routes.py` | World project status | None | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/restore` | `rpg_world_routes.py` | World project status | None | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/authorship-audit/remediate` | `rpg_world_routes.py` | World draft authorship metadata | Draft revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/drafts/{source_draft_revision}/restore` | `rpg_world_routes.py` | World draft (restored as a new draft revision) | Source draft revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/revisions` | `rpg_world_routes.py` | Published world revision | Draft revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/revisions/{world_revision}/releases` | `rpg_world_routes.py` | World release | World revision | Exemption, world authoring |
| `POST /api/rpg/scenarios` | `rpg_world_routes.py` | New scenario project | New id | Exemption, world authoring |
| `POST /api/rpg/scenarios/{scenario_id}/archive` | `rpg_world_routes.py` | Scenario status | None | Exemption, world authoring |
| `POST /api/rpg/scenarios/{scenario_id}/restore` | `rpg_world_routes.py` | Scenario status | None | Exemption, world authoring |
| `POST /api/rpg/scenarios/{scenario_id}/revisions` | `rpg_world_routes.py` | Published scenario revision | Scenario draft | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}` | `rpg_world_authoring_routes.py` | World metadata draft | `expected_draft_revision` | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}/topics/{topic_id}` | `rpg_world_authoring_routes.py` | World topic draft | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}` | `rpg_world_authoring_routes.py` | World entity draft | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate` | `rpg_world_authoring_routes.py` | Model call, world entity draft | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/restore` | `rpg_world_authoring_routes.py` | World topic draft (restored) | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/enrich-dossiers` | `rpg_world_dossier_routes.py` | Model calls, world entity dossiers | Draft revision | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/dossier` | `rpg_world_dossier_routes.py` | World entity dossier | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier-preview` | `rpg_world_dossier_routes.py` | Model call; returns a preview, writes nothing | `expected_draft_revision` and `expected_content_hash` | Exemption, read-only |
| `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier` | `rpg_world_dossier_routes.py` | Model call, world entity dossier | `expected_draft_revision` and `expected_content_hash` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/topics` | `rpg_world_library_routes.py` | World topic | `expected_revision` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/map-blueprints/materialize` | `rpg_world_library_routes.py` | World map blueprints for locations without one | None | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/map-blueprints/{map_id}` | `rpg_world_library_routes.py` | One world map blueprint | Blueprint revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/generation` | `rpg_world_library_routes.py` | World generation run and `rpg.world.topic.generate` jobs | Run id | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/retry-failed` | `rpg_world_library_routes.py` | Generation run, retried topic jobs | Run state | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/continue` | `rpg_world_library_routes.py` | Generation run, next topic jobs | Run state | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/publish` | `rpg_world_library_routes.py` | World revision and release from a run | Run state | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/repair-for-launch` | `rpg_world_library_routes.py` | World drafts repaired for launch readiness | Draft revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/prepare-openings-for-launch` | `rpg_world_library_routes.py` | Opening scenarios | Draft revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/starter-bubble/promote` | `rpg_world_library_routes.py` | World revision (starter area promoted) | Source revision | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/retry-review` | `rpg_world_generation_review_routes.py` | Generation run, retried topic jobs | Retry budget | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/results/{topic_id}/accept` | `rpg_world_generation_review_routes.py` | Accepted topic result into the world draft | `expected_candidate_hash` | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/accept-all` | `rpg_world_generation_review_routes.py` | Accepted topic results | Candidate hashes | Exemption, world authoring |
| `POST /api/rpg/world-generation/{run_id}/results/{topic_id}/decision` | `rpg_world_generation_review_routes.py` | Retry decision for a topic | Run state | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/image-generation` | `rpg_world_image_routes.py` | Image provider calls, world image assets and targets | Target revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/image-prompts/regenerate` | `rpg_world_image_routes.py` (path held in `_PROMPT_1`) | Model call, world image prompts | None | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}/image-targets/{target_id:path}` | `rpg_world_image_routes.py` | One image target | Target revision | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/image-targets/{target_id:path}/regenerate` | `rpg_world_image_routes.py` | Image provider call, one image asset | Target revision | Exemption, world authoring |
| `PATCH /api/rpg/worlds/{world_id}/genre-profile` | `rpg_world_profile_routes.py` | World genre profile review | `expected_profile_revision` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/genre-profile/approve` | `rpg_world_profile_routes.py` | World genre profile approval | `expected_profile_revision` | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/genre-profile/retry` | `rpg_world_profile_routes.py` | `rpg.world.profile.generate` job | Profile state | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/deferred-locations/{location_id}/materialize` | `rpg_progressive_map_routes.py`, `genesis/worlds/progressive_materialization.py` | New world revision with the location's map | `source_world_revision`; next revision under lock | Exemption, world authoring |
| `POST /api/rpg/worlds/{world_id}/materialization-jobs/schedule` | `rpg_progressive_map_routes.py` | `rpg.world.map.materialize` jobs | `create_job_once` | Exemption, world authoring |
| `POST /api/rpg/worlds/import` | `rpg_world_bundle_routes.py` | World tables and assets from a bundle | Bundle hash; new or given world id | Exemption, import |
| `DELETE /api/rpg/worlds/{world_id}` | `rpg_world_deletion_routes.py`, `genesis/worlds/lifecycle_service.py` | Deletes the world project, its jobs and map definitions, **and every campaign bound to it** (`DELETE FROM omnix_rpg_campaigns ... IN (bindings)`) with their map instances | Acknowledgement plus the world's exact title (`confirmation_title`) | Exemption, admin (deletion). Deleting campaigns is a campaign write outside the pipeline; RQ-8.10 retention should own it |
| `POST /api/rpg/world-catalog/{entry_id}/install` | `rpg_world_sharing_routes.py` | World tables from the community catalog | Catalog entry | Exemption, import |
| `POST /api/rpg/worlds/{world_id}/adopt` | `rpg_world_sharing_routes.py` | A copy of a shared world | Source revision | Exemption, adoption |
| `POST /api/rpg/worlds/{world_id}/share` | `rpg_world_sharing_routes.py` | Publishes a world to GitHub; sharing records | None | Exemption, library and sharing |
| `PUT /api/rpg/world-sharing/github/token` | `rpg_world_sharing_routes.py` | The user's GitHub token | None | Exemption, admin (credentials) |
| `POST /api/rpg/world-sharing/github/device` | `rpg_world_sharing_routes.py` | A GitHub device sign-in flow | Flow id | Exemption, admin (credentials) |
| `POST /api/rpg/world-sharing/github/device/{flow_id}/poll` | `rpg_world_sharing_routes.py` | The GitHub token when the flow completes | Flow id | Exemption, admin (credentials) |
| `DELETE /api/rpg/world-sharing/github` | `rpg_world_sharing_routes.py` | Removes the GitHub token | None | Exemption, admin (credentials) |

## Tools and diagnostics

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/rpg/debug/event` | `rpg_debug_routes.py` | A log event only | None | Exemption, read-only (logging) |
| `POST /api/rpg/map-instances/{map_instance_id}/performance-profile` | `rpg_grid_performance_routes.py`, `world/grid_runtime_performance_service.py` | Nothing: profiles the grid runtime and counts map events | None | Exemption, read-only |
| `POST /api/rpg/map-editor/validate` | `rpg_map_editor_routes.py` | Nothing: validates the posted definition | None | Exemption, read-only |
| `POST /api/rpg/map-editor/apply` | `rpg_map_editor_routes.py`, `world/map_content_editor.py` | Nothing: applies operations to the posted definition and returns it | None | Exemption, read-only |
| `POST /api/rpg/map-editor/export` | `rpg_map_editor_routes.py` | Nothing: returns the posted definition as a file | None | Exemption, read-only |

## Compatibility router (`edge/api/compat_router.py`)

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/rpg/session/get` | `edge/api/payloads/genesis_sessions.py`, `edge/api/payloads/sessions.py` | **Multi-action.** By `action`: `new_game` and `start_preset` create a campaign; `rename` and `delete` as their typed routes; `loadout_action`, `item_action`, `item_command`, `item_resolve`, `item_diagnostics` (with `record`), `item_maintenance` (without `dry_run`) and `item_scenario` (with `run`) change the campaign document by out-of-turn `save_session`; `continue`, `item_detail`, `ability_detail` and `item_objectives` read. The web client still calls it (`rpgSessionClient.ts`, `rpgItemApi`) | Loaded revision only | Split: creation actions exempt (campaign creation); the item and loadout actions become `structured_action` through the typed routes; the rest read-only. Retire the route when the client no longer uses it |
| `POST /api/rpg/session/list` | `edge/api/payloads/sessions.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/validate` | `edge/api/payloads/adventure.py` | Nothing: validates the posted setup | None | Exemption, read-only |
| `POST /api/rpg/adventure/preview` | `edge/api/payloads/adventure.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/inspect-world` | `edge/api/payloads/adventure.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/inspect-world-snapshot` | `edge/api/payloads/adventure.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/compare-world` | `edge/api/payloads/adventure.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/compare-entity` | `edge/api/payloads/adventure.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/adventure/simulate-step` | `edge/services/adventure_world_service.py` | Nothing persistent: simulates a step of the posted setup | None | Exemption, read-only |
| `POST /api/rpg/adventure/simulation-state` | `edge/services/adventure_world_service.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/inspect/timeline` | `edge/api/payloads/inspection.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/inspect/timeline_tick` | `edge/api/payloads/inspection.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/inspect/tick_diff` | `edge/api/payloads/inspection.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/inspect/npc_reasoning` | `edge/api/payloads/inspection.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/inspect/world_events` | `edge/api/payloads/inspection.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/player/state` | `edge/api/payloads/player.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/player/journal` | `edge/api/payloads/player.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/player/codex` | `edge/api/payloads/player.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/player/objectives` | `edge/api/payloads/player.py` | Nothing | None | Exemption, read-only |
| `POST /api/rpg/player/encounter` | `edge/api/payloads/player.py` | Nothing | None | Exemption, read-only |

## Hermes (`edge/hermes`)

| Entry point | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `POST /api/hermes/rpg/approved-flow` | `edge/hermes/approved_routes.py`, `canonical_submitter.py` | When enabled, submits an approved command as a turn: `interactive_first_call_runtime.apply_turn` with `session_override`, `narration_mode: "blocking"`, not a job keyed by `submission_id` | None of its own; the turn's saves | `structured_action` (Hermes command), through the pipeline with a submission id |
| `POST /api/hermes/rpg/sequence/execute-step` | `edge/hermes/sequence_approved_executor.py` | Submits one approved step through the canonical submitter, as approved-flow; writes the sequence state file | Loop guard; none for the campaign | `structured_action` (Hermes command) |
| `POST /api/hermes/rpg/sequence/review` | `edge/hermes/approved_routes.py`, `sequence_state.py` | The sequence state in a local JSON file (`resources_data_root()/hermes_rpg_sequences.json`), not the database | None | Exemption, admin (developer tooling); the file store is process-local state for RQ-8 to move or retire |
| `POST /api/hermes/rpg/sequence/plan` | `edge/hermes/sequence_planner_loop.py` | Nothing: model-planned sequence | None | Exemption, read-only |
| `POST /api/hermes/rpg/context-pack` | `edge/hermes/context_pack.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/rpg/narrative-research` | `edge/hermes/narrative_research.py` | Nothing: bounded research over the campaign bible | None | Exemption, read-only |
| `POST /api/hermes/test` | `edge/hermes/api.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/adapter/preview` | `edge/hermes/api.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/rpg/context` | `edge/hermes/api.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/rpg/suggestions` | `edge/hermes/api.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/rpg/turn-readout` | `edge/hermes/api.py` | Nothing | None | Exemption, read-only |
| `POST /api/hermes/plan` | `edge/hermes/plan.py` | Nothing: a model plan, validated, `state_changed: false` | None | Exemption, read-only |
| `POST /api/hermes/approve` | `edge/hermes/api.py` | Nothing: always answers `mode: "blocked"` | None | Exemption, read-only |
| `POST /api/hermes/lookup` | `edge/hermes/api.py` | Nothing: `dry_run: true` | None | Exemption, read-only |

## Job kinds

| Job kind | Module | Writes | Concurrency | Turn kind or exemption |
|---|---|---|---|---|
| `rpg.turn` | `session/jobs/handlers.py`, `session/jobs/turn_executor.py` | The turn, as the turn route (§3 pipeline), when it runs as a job | Submission policy (`_rpg_submission_policy`), `submission_id`; campaign revision at commit | `player_text` (the job form of the turn route) |
| `rpg.narration` | `session/narration_jobs.py`, `session/jobs/narration_job.py` | Finished narration into `runtime_state.narration_artifacts` by `save_runtime_session`: an out-of-turn revision with no turn row (`narration_jobs.py:153`) | Loaded revision | Pipeline steps 8–10: finalize inserts the narrative response and marks the delivery final, with no campaign save (§4.1) |
| `rpg.scene_lore` | `genesis/forge/scene_lore_job.py`, `runtime_lore_store.enrich_scene_lore` | Model calls, then `omnix_rpg_campaign_bibles` (newcomers' dossiers, new canon revision) | Bible `expected_revision` under lock | Exemption, canon follow-up (§4.1 step 11); writes canon only |
| `rpg.report.last10` | `session/jobs/last10_report.py` | The job's own output (a report over recent turns) | None | Exemption, read-only |
| `rpg.campaign_genesis.generate` | `genesis/forge/async_coordinator.py` (background worker `rpg_campaign_genesis`) | Generated canon, then the campaign document by `sessions.save` (the session materialized from the World Forge), creation progress | Job id per campaign | Exemption, campaign creation (before the first turn) |
| `rpg.campaign_world.expand` | `genesis/forge/async_coordinator.py` | More generated canon after launch, then the campaign document by `sessions.save` and expansion progress: an out-of-turn save that can land while the player is playing | Job id per campaign; loaded revision | **Open.** Not campaign creation once the first turn has run. Proposal: its result becomes proposals folded in by the next turn, like narration side effects (§4.1); needs a decision in RQ-1 |
| `rpg.world.topic.generate` | `genesis/worlds/generation_worker.py` | World generation topic results | Run and job state | Exemption, world authoring |
| `rpg.world.profile.generate` | `genesis/worlds/generation_worker.py` | World genre profile | Profile revision | Exemption, world authoring |
| `rpg.world.map.materialize` | `genesis/worlds/progressive_materialization_worker.py` | New world revision with a materialized location map | Source world revision | Exemption, world authoring |

`rpg.new_game.create` is the type of a creation progress envelope (`genesis/creation_progress.py`), not a durable job.

## In-turn writers and paths with no entry point

- **Ambient ticks.** "wait", "listen" and the other ambient commands (`is_ambient_tick_command`) run inside the turn
  route (`turn_action_resolution`, `turn_world_resolution`); their state rides on the turn. They become part of the
  `world_tick` step (§4.1 step 6).
- **Idle resume.** `session/idle_narration_delivery.py` (`apply_idle_tick`, `apply_idle_ticks`,
  `apply_resume_catchup`) loads and saves with `save_runtime_session` (lines 219, 280, 342), but no route, job or
  other module calls these functions today: idle catch-up is not reachable in production. `/continue` only loads. The
  `world_tick` turn for time away (§4.5) is therefore new behaviour, not a move of an existing path.
- **Out-of-turn saves inside the turn route.** `player_turn_execution` early returns (§3) and the narration-artifact
  writers (`semantic_response_projection.py`, `companion_turn_runtime.py`, `turn_bound_narration.py`) are inside the
  turn route, listed in §3, and move with RQ-1.4.

## Counts

- 116 mutating routes: 18 play actions and campaign tools, 7 creation and binding, 52 world authoring, library and
  sharing, 5 tools, 20 compatibility, 14 Hermes; and 9 job kinds.
- Proposed turn kinds: `player_text` 1 route (+ `rpg.turn`); `structured_action` 9 routes (loadout, map actions,
  tactical move and attack, geometry patches, observe, lore discovery, Hermes approved flow and execute-step) plus the
  item and loadout actions of `/api/rpg/session/get`; `world_tick` 2 (`continue`, `spatial-ticks`); `system` none
  (the schema upcast has no route).
- Out-of-turn campaign document saves reachable from routes or jobs today: loadout, map actions, lore (three routes,
  projection save), rename, delete (SQL), the compatibility multi-action route, the local dialogue fixture,
  `rpg.narration`, `rpg.campaign_genesis.generate` and `rpg.campaign_world.expand`.
