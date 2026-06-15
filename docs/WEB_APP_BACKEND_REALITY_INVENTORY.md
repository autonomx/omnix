# Omnix Web App Backend Reality Inventory

Last updated: 2026-06-14

Scope: Phase 3 of `docs/WEB_APP_REDESIGN_ROADMAP.md`.

This document inventories the backend systems that already exist before the web
app redesign consolidates them behind shared platform services. It is
documentation-only: no queue, registry, asset, prompt, replay, or persistence
behavior is changed by this phase.

## Consolidation Decisions

These are the Phase 3 feasibility conclusions that later implementation phases
should use as starting assumptions:

- Jobs: use the image claim/lease queue shape as the reference concurrency
  pattern, but not its current in-memory storage. Preserve TTS chunk ordering as
  job stages/checkpoints. Treat RPG narration jobs as runtime-state-backed work
  to wrap before replacing.
- Providers: build one provider/model facade over the existing LLM and audio
  registries. Do not introduce a third discovery registry. Image and RPG visual
  providers should become capability adapters behind the facade.
- Assets: use the image asset store's content-addressed file plus manifest
  model as the reference shape, then generalize it for audio, reports,
  transcripts, checkpoints, sessions, and voice assets.
- Prompts: add shared prompt/template metadata and rendering helpers around
  existing prompt builders first. Do not extract RPG-specific semantics into a
  platform prompt engine.
- Replay and persistence: treat RPG durable sessions, LLM recording, replay
  validation, state hashing, and checkpoint artifacts as reference
  implementations. Platformize them by wrapping and publishing typed contracts
  before moving storage or replay internals.

## Jobs and Workers

| Implementation | Owner module | Current behavior | Likely consolidation target |
| --- | --- | --- | --- |
| `src/app/job_queue.py` | Voice / TTS | In-memory thread-backed queue with `pending`, `processing`, `completed`, and `failed` status, cancellation, retries, result polling, completed-result cache, and chunk reassembly support. | Wrap behind shared jobs as a staged TTS workflow. Preserve chunk ordering/reassembly as stage checkpoints. |
| `src/app/image/job_queue.py` | Image generation | Global in-memory image queue with claim/lease tokens, lease expiration, complete/fail/release helpers, and list/read helpers. | Reference queue concurrency shape for shared jobs. Replace storage with durable job records later. |
| `src/app/rpg/visual/job_queue.py` | RPG visual generation | Compatibility wrapper over the global image queue that preserves RPG fields such as `session_id` and `request_id`. | Feature adapter over the shared job API. Keep compatibility payloads until RPG visual callers are migrated. |
| `src/app/rpg/visual/queue_runner.py` | RPG visual generation | Claims visual jobs, skips stale requests, loads/saves RPG sessions from durable storage, calls image generation, and writes generated assets. | Worker adapter that consumes shared jobs and emits shared asset references while preserving RPG session updates. |
| `src/app/rpg/visual/background_runner.py` | RPG visual generation | Polling background thread around the visual queue runner. | Local executor adapter during the shared job transition. |
| `src/app/rpg/session/narration_worker.py` | RPG narration | Manager and subscriber layer for narration processing. It explicitly does not own the authoritative queue; jobs live in `runtime_state["narration_jobs"]` and `runtime_state["narration_jobs_by_turn"]`. | Runtime-state job projection with shared event/status exposure before any queue migration. |
| `src/tests/rpg/autoplay_llm_campaign.py`, `src/tests/rpg/interactive_cli_campaign.py` | RPG operator runs | Local/manual/autoplay harnesses that write reports, transcripts, ZIPs, and checkpoints under test-results style output directories. | Report/run job model after gateway and artifact contracts exist. These are operator harnesses, not a production queue. |
| `src/app/rpg/autoplay_performance_artifacts.py`, `src/app/rpg/autoplay_report_size_guard.py`, `src/app/rpg/autoplay_report_materialization_guard.py` | RPG report artifacts | Post-run artifact writers and guards for autoplay performance/report outputs. | Shared report/artifact post-processing stages. |
| `src/app/rpg/session/survival_autoplay*.py` | RPG simulation/autoplay | In-runtime autoplay and simulation helpers with many deterministic artifact payloads. | Keep as RPG runtime/test helpers; expose outputs through shared jobs/assets only when a browser-facing run API needs them. |

### Jobs Feasibility

Reference implementation: `src/app/image/job_queue.py` has the best primitive
for concurrent worker safety because claim/lease ownership is explicit. It
should inspire the shared job executor API, while SQLite or another durable
local store should own persistence.

Incompatible assumptions:

- Current queues are in-memory and single-process.
- TTS is thread/worker-function oriented and result-cache oriented; image is
  claim/lease oriented; narration is embedded in RPG session runtime state.
- Resource classes, GPU locks, CPU/network concurrency, cancellation semantics,
  logs, and stage checkpoints are not represented consistently.
- RPG visual jobs currently update durable RPG sessions as part of job
  processing, which means job migration must preserve session side effects.

Data migration requirements:

- Existing generated images and `manifest.json` must remain readable.
- Existing RPG visual request fields must remain accepted during the wrapper
  period.
- TTS completed audio/result cache does not appear durable; migration should not
  claim old in-memory jobs can be recovered.
- Existing RPG sessions may contain narration/visual runtime job metadata; read
  paths must tolerate it during and after migration.

Tests needed before consolidation:

- Image claim/lease stale lease, complete/fail/release, and compatibility-wrapper
  tests.
- TTS chunk ordering/reassembly and cancellation tests.
- RPG visual stale-request skip, session-not-found handling, asset-write, and
  session-save tests.
- Narration runtime-state job projection tests that prove no replay or turn
  determinism changes.

Rollback path:

- Keep adapters over the existing queues until the shared job table is proven.
- The image wrapper can route back to `src/app/image/job_queue.py`.
- TTS can keep its existing queue public surface while new jobs are shadowed.
- RPG narration should keep `runtime_state` as the source of truth until a
  deterministic replay gate proves otherwise.

## Provider Registries

| Implementation | Owner module | Current behavior | Likely consolidation target |
| --- | --- | --- | --- |
| `src/app/providers/registry.py` | LLM providers | Dynamic discovery of `BaseProvider` subclasses, provider metadata/capabilities, `ProviderConfig`, and provider creation helpers. | Reference discovery/capability pattern for the shared provider facade. |
| `src/app/providers/audio_registry.py` | Audio providers | Separate dynamic discovery for `BaseTTSProvider` and `BaseSTTProvider`, audio-specific config, list/create helpers, and registration helpers. | Adapter behind the shared facade for TTS and STT capabilities. |
| `src/app/image/providers/registry.py` | Image generation | Static list of image providers such as `flux_klein` and `mock`; validates provider keys but does not create provider instances. | Capability listing adapter; factory behavior should be supplied by the shared provider facade or existing visual provider factories. |
| `src/app/rpg/visual/providers/registry.py` | RPG visual generation | Factory registry for `disabled` and `flux_klein`, environment/settings resolution, and runtime validator metadata. | Image capability factory adapter. Preserve disabled/off behavior and validator metadata. |
| `src/app/shared.py` | Cross-cutting settings/provider access | Loads and migrates settings, reads secrets, builds cached LLM/TTS/STT provider instances, and exposes image/RPG visual settings. | Settings and provider cache compatibility boundary for the shared facade. |

### Providers Feasibility

Reference implementation: `src/app/providers/registry.py` is the most general
registry because it already has dynamic discovery, metadata, capabilities, and a
provider config object. The audio registry should not be deleted first; it
should be wrapped as the audio capability provider until a single config model
exists.

Incompatible assumptions:

- LLM, TTS, STT, image, and RPG visual providers use different base classes and
  config shapes.
- `src/app/shared.py` creates singleton provider instances from settings, while
  registries create provider instances directly.
- Image provider listing and RPG visual provider factories are split.
- Provider health, model discovery, GPU residency, and worker process ownership
  are not normalized.

Data migration requirements:

- `resources/data/settings.json` must keep loading through `migrate_settings`.
- Existing provider keys such as `lmstudio`, `openrouter`, `cerebras`,
  `llamacpp`, `faster-qwen3-tts`, `parakeet`, `flux_klein`, `mock`, and
  `disabled` need compatibility aliases or explicit diagnostics.
- Secrets lookup must not be moved into generated frontend contracts.

Tests needed before consolidation:

- Registry discovery/list/create tests for LLM and audio providers.
- Settings migration tests covering provider, audio, image, and RPG visual
  fields.
- Provider facade tests for capability lookup, disabled providers, missing
  workers, and health envelopes.
- Compatibility tests proving existing `shared.py` provider getters still work
  through the facade.

Rollback path:

- Keep `src/app/shared.py` and existing registries as compatibility delegates.
- The first facade implementation should be additive: new API reads from the
  facade, legacy routes keep their existing helpers until parity tests pass.

## Assets, Artifacts, and Data Stores

| Implementation | Owner module | Current behavior | Likely consolidation target |
| --- | --- | --- | --- |
| `src/app/runtime_paths.py` | Platform paths | Canonical repo/resource roots including `resources/data`, `generated_images`, `rpg_sessions`, `test-results`, and `models`. | Reference path helper layer for shared stores. |
| `src/app/image/asset_store.py` | Image generation | Saves generated images under `resources/data/generated_images`, uses content-hash filenames, tracks logical asset IDs in `manifest.json`, and cleans unused files. | Reference asset manifest and content-addressed file model. |
| `src/app/rpg/visual/asset_store.py` | RPG visual generation | Compatibility wrapper over the global image asset store. | Feature adapter over shared assets. |
| `src/app/rpg/session/durable_store.py` | RPG sessions | Disk-backed RPG sessions under `resources/data/rpg_sessions`, legacy path migration, atomic writes, Windows retry/backoff, corrupt JSON quarantine, and payload migration. | Reference durable JSON read/write and compatibility strategy for session-like stores. |
| `src/app/rpg/persistence/save_packaging.py` | RPG saves | Stable save package serialization and digest helpers for package-style persistence. | Reference for versioned, digestable exported packages. |
| `src/app/shared.py` | Settings, models, voice assets | Owns `resources/data/settings.json`, `resources/voice_clones/voice_clones.json`, `resources/models`, `resources/logs`, and voice clone metadata helpers. | Compatibility input for shared settings/assets/model registry. |
| `docs/rpg_saved_certification_runbook.md` and `src/tests/rpg/manual/*` | RPG saved certification | Defines operator artifact expectations under `resources/data/test-results/<run-id>`: reports, transcripts, final/loadable state, certification payload, ZIPs, and diagnostics. | Reference report/run artifact contract. |
| `src/tests/rpg/interactive_cli_campaign.py` and `src/tests/rpg/interactive_cli_campaign_state.py` | RPG interactive operator runs | Writes interactive transcript, report HTML, performance data, ZIPs, and state checkpoint manifests. | Shared run/report artifact producers after job and asset APIs exist. |
| `src/app/rpg/autoplay_performance_artifacts.py`, `src/app/rpg/autoplay_report_size_guard.py`, `src/app/rpg/autoplay_report_materialization_guard.py` | RPG autoplay reports | Structured performance/report artifacts and size/materialization guards. | Shared report artifact post-processing and diagnostics. |

### Assets Feasibility

Reference implementation: the image asset store is the simplest reusable
content-addressed manifest shape, while durable RPG sessions are the reference
for safe disk writes and corruption handling.

Incompatible assumptions:

- Image assets use one `manifest.json`; RPG sessions are one JSON file per
  session; operator runs are directory/ZIP bundles; voice profiles use a
  separate JSON file under `resources/voice_clones`.
- Some artifact writers live in tests/operator harnesses but produce real
  files that users inspect.
- There is no shared asset identity model for uploaded files, generated files,
  reports, transcripts, checkpoints, voice samples, and model files.
- Cleanup rules differ: image store has unused-file cleanup, report/test output
  explicitly should not be committed, and sessions should not be garbage
  collected without user action.

Data migration requirements:

- Preserve `resources/data/generated_images/manifest.json` and existing image
  file paths.
- Preserve `resources/data/rpg_sessions` and legacy session read-through.
- Preserve `resources/data/settings.json`, `resources/voice_clones`, and model
  directory conventions.
- Preserve operator output expectations under `resources/data/test-results` and
  do not silently relocate reports/checkpoints without compatibility links or
  diagnostics.

Tests needed before consolidation:

- Asset manifest read/write and cleanup tests.
- RPG durable session save/load, corrupt quarantine, legacy migration, and
  atomic write tests.
- Saved certification artifact discovery and ZIP verifier tests.
- Settings and voice clone metadata round-trip tests.
- Migration dry-run tests over representative manifests/sessions/settings.

Rollback path:

- Keep shared assets as read-through wrappers initially.
- Do not move files during the first shared API phase; return references to
  existing paths.
- Any later migration should be copy-first with dry-run diagnostics and an
  explicit old-path rollback plan.

## Prompt and Template Builders

| Implementation | Owner module | Current behavior | Likely consolidation target |
| --- | --- | --- | --- |
| `src/app/rpg/session/memory_prompt.py` | RPG memory/prompting | Builds deterministic, bounded relevant-memory context with `format_version` and renders prompt blocks. | Reference prompt context metadata/versioning pattern. |
| `src/app/rpg/ai/world_scene_narrator_prompts.py` | RPG narration | Builds scene narration prompts, injects relevant-memory and memory-grounding blocks, defines JSON format expectations such as `rpg_narration_v2` and candidate envelopes. | Wrap with shared prompt metadata while preserving RPG grounding rules. |
| `src/app/rpg/ai/semantic_action_intelligence.py`, `src/app/rpg/ai/action_intelligence.py` | RPG intent/action intelligence | Builds action-intelligence and semantic-action prompts with grounding diagnostics and turn-context instructions. | Prompt contract wrappers for RPG action classification. |
| `src/app/rpg/ai/dialogue/dialogue_prompt_builder.py`, `src/app/rpg/ai/conversation_prompt_builder.py`, `src/app/rpg/presentation/dialogue_prompt_builder.py` | RPG dialogue | Builds NPC dialogue/conversation prompts and presentation-facing dialogue instructions. | RPG-owned prompt builders with shared rendering/version metadata. |
| `src/app/rpg/prompting/builder.py` | RPG legacy prompting | Simple f-string prompt builder returning strict JSON instructions from NPC/scene/memory objects. | Legacy prompt to keep isolated or retire after coverage proves no callers need it. |
| `src/app/rpg/templates/campaign_templates.py`, `src/app/rpg/creator/defaults.py` | RPG campaign setup | Defines campaign/adventure setup templates and start payloads. | Shared template catalog shape only if non-RPG modules need comparable setup templates. |
| `src/app/rpg/story_authoring/prompts.py` | RPG/story authoring | Story authoring prompt helpers. | Story/RPG prompt adapter behind shared metadata. |
| `src/audiobook/ai/ai_structuring_service.py`, `src/audiobook/ai/character_extractor.py`, `src/audiobook/ai/dialogue_parser.py`, `src/audiobook/ai/emotion_detector.py` | Audiobook/story processing | Prompt constants and JSON instructions for structure extraction, character extraction, dialogue parsing, and emotion detection. | Audiobook prompt wrappers with shared versioning and parse diagnostics. |
| `src/audiobook/director/scene_mood_engine.py`, `src/audiobook/voice/voice_classifier.py` | Audiobook direction/voice | Mood and voice-classification prompt templates. | Audiobook prompt wrappers with shared metadata. |

### Prompts Feasibility

Reference implementation: `src/app/rpg/session/memory_prompt.py` has the
clearest platform-worthy shape because it returns a bounded structured context
with a `format_version`, source, usage, query metadata, and deterministic
rendering. `src/app/rpg/ai/world_scene_narrator_prompts.py` is the reference
for grounding-sensitive prompt contracts, but its semantics must remain RPG
owned.

Incompatible assumptions:

- Some prompts are structured payload builders; others are raw module-level
  string constants or f-strings.
- Format/version fields are common in RPG runtime payloads but inconsistent in
  older prompt builders and audiobook prompts.
- JSON parse/repair expectations are scattered across callers.
- Prompt builders sometimes include authoritative runtime rules that should not
  become generic platform copy.

Data migration requirements:

- Prompt migration is mostly behavioral, not file migration.
- Any saved replay/capture record that keys on prompt text can drift if prompt
  rendering changes, so wrappers must preserve rendered text until replay tests
  are updated deliberately.

Tests needed before consolidation:

- Golden or shape tests for relevant memory prompt, scene prompt, semantic
  action prompt, dialogue prompt, and audiobook JSON prompts.
- Replay/capture tests proving prompt wrapper metadata does not alter old
  prompt text unless a version bump is intentional.
- JSON parse/error diagnostics tests for strict-output prompts.

Rollback path:

- Add metadata wrappers that call existing builders.
- Keep old rendered prompt text as the compatibility output until each feature
  has acceptance tests and updated replay records.

## Replay, Persistence, Hashing, and Checkpoints

| Implementation | Owner module | Current behavior | Likely consolidation target |
| --- | --- | --- | --- |
| `src/app/rpg/core/llm_recording.py` | RPG deterministic LLM | Records provider outputs keyed by stable JSON prompt/context/config and strictly refuses missing replay records. | Reference provider-request recording/replay primitive. |
| `src/app/rpg/orchestration/capture.py`, `src/app/rpg/orchestration/replay.py` | RPG LLM orchestration | Persists completed provider results into runtime orchestration state and finds replayable completed requests by request or turn ID. | Runtime-level replay artifact adapter. |
| `src/app/rpg/core/replay_engine.py` | RPG core simulation | Replays recorded events through a fresh loop, supports deterministic mode, branch replay, snapshot/hybrid replay concepts, and replay-safe side-effect controls. | Conceptual reference for event replay, kept RPG scoped. |
| `src/app/rpg/validation/state_hash.py`, `src/app/rpg/validation/replay_validator.py`, `src/app/rpg/validation/simulation_parity.py`, `src/app/rpg/validation/determinism.py` | RPG validation | Stable state hashing, replay validation, simulation parity, and determinism checks. | Reference validation gates for future platform replay contracts. |
| `src/app/rpg/session/durable_store.py`, `src/app/rpg/session/migrations.py` | RPG sessions | Disk-backed session read/write with migration and corruption handling; session payload migration guarantees required sub-states. | Reference durable session persistence and migration style. |
| `src/app/rpg/persistence/migration_manager.py` | RPG save packages | Migrates save packages from schema v1 through current schema with explicit version advancement. | Reference versioned migration manager for exported packages. |
| `src/app/rpg/interactive_cli_state_checkpoint.py`, `src/app/rpg/interactive_cli_live_state.py` | RPG interactive CLI checkpoints | Creates checksum-backed checkpoint envelopes, serializes/deserializes durable checkpoint files, and attaches checkpoints to live turns. | Reference checkpoint envelope and checksum strategy. |
| `docs/rpg_saved_certification_runbook.md`, `src/tests/rpg/test_ci_phase7_*` | RPG saved certification | Provider-free gates for saved certification payloads, report diagnostics, artifact discovery, ZIP verification, and checkpoint/state digest mismatch diagnostics. | Reference operator-facing replay/persistence evidence contract. |
| `src/tests/rpg/autoplay_llm_campaign.py` | RPG autoplay harness | Optional/local live-provider campaign harness that can validate save/load checkpoints and emit artifacts. | Optional evidence producer; not a required platform runtime dependency. |

### Replay and Persistence Feasibility

Reference implementation: RPG owns the strongest deterministic persistence
contracts. The shared platform should publish these as typed API/artifact
contracts before moving internals.

Incompatible assumptions:

- Replay is deeply tied to RPG event-loop concepts, runtime state, and provider
  recording rules.
- Some replay evidence is provider-free CI; live 100-turn/autoplay evidence is
  optional local operator output.
- Disk session persistence, package persistence, interactive checkpoints, and
  certification artifacts use different envelopes and version fields.
- Prompt text changes can invalidate LLM replay keys.

Data migration requirements:

- RPG session files and save packages must remain readable.
- Corrupt session quarantine behavior must be preserved.
- Checkpoint and digest fields must remain source-backed; missing digests should
  stay explicit blockers, not inferred successes.
- Replay/capture artifacts need a compatibility reader before any storage move.

Tests needed before consolidation:

- Existing replay validator, state hash, save/load round-trip, session migration,
  and saved certification gates.
- Focused tests for any new API wrapper around session load/save, replay
  artifact lookup, and checkpoint digest reporting.
- Prompt-wrapper replay tests whenever rendered prompt text changes.

Rollback path:

- Keep RPG replay/persistence internals in place.
- Expose platform APIs as delegates first.
- If platform wrappers fail, route callers back to RPG-owned helpers and keep
  saved artifacts/readers unchanged.

## Phase 3 Readiness for Later Phases

Phase 3 confirms that consolidation should proceed in this order:

1. FastAPI gateway foundation and OpenAPI exposure.
2. Worker health and provider facade contracts.
3. OpenAPI type generation.
4. Resource-aware job schema and scheduler contract.
5. Job queue consolidation using a durable implementation of the claim/lease
   pattern.
6. Provider facade consolidation over the existing LLM/audio/image registries.
7. Shared asset library with read-through compatibility for current paths.
8. Prompt metadata wrappers around existing builders.
9. Replay/persistence wrappers that preserve RPG deterministic gates.

The main risk remains data compatibility, not code organization. Later phases
should prefer read-through adapters, dry-run migrations, and source-backed
diagnostics before moving user-owned files or changing deterministic RPG replay
behavior.
