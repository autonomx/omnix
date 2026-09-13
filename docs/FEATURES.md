# Omnix Feature Catalog

This document catalogs the implemented Omnix application surface. It covers routed workspaces as well as important capabilities embedded inside Chat, Settings, the shared platform layer, and the generalized agent runtime.

A feature can be implemented even when it is not a top-level route. Conversely, configuration or backend compatibility code is not described here as a user-facing feature unless the current application exposes or consumes it.

## Shared application shell

Every browser workspace runs inside the same React application shell.

- Shared sidebar and primary-mode switcher.
- TanStack Router route ownership and `/` → `/chatbot` default navigation.
- Shared appearance handling for light/dark/system mode, theme palette, text scaling, density/motion/accessibility preferences where configured.
- Shared typed API client and TanStack Query server-state cache.
- Shared event client for job/runtime updates.
- Shared design primitives, loading/error/empty states, status pills, cards, audio controls, and workspace panels.
- Global provider/model, job/run, asset/artifact, settings, and diagnostics infrastructure.

## Chat and Assistant — `/chatbot`

Chat is both a conversational workspace and the primary surface for Omnix assistant/agent capabilities.

### Sessions and messages

- Create, select, persist, and revisit chat sessions.
- Provider/model selection through the shared provider facade.
- Streaming assistant responses and job-backed generation.
- Conversation history backed by server-owned session data.
- Interrupt/recovery handling for active and abandoned generation jobs.
- Suggested prompts and configurable assistant personality.
- Message feedback and activity/run presentation.

### Attachments and artifacts

- Paste PNG, JPEG, or WebP images into a message.
- Up to eight pasted image attachments; each image is bounded to 5 MB by the current UI.
- Paste small text files for contextual analysis; the current UI bounds pasted text files to 100 KB.
- HTML artifact preview support.
- Markdown and research-report rendering, including deep-research presentation.

### Voice sessions and live conversation

- Browser speech-recognition capture where supported.
- STT service integration for speech input.
- TTS service integration for spoken assistant output.
- Streaming TTS playback and interruption handling.
- Fullscreen live-chat experience.
- Voice sensitivity and voice-profile selection.
- Live-call diagnostics and turn-performance instrumentation.
- Voice calibration, durable evaluation, session evaluation, and voice-governance panels used by the live conversation stack.

### Assistant identity and characters

- System vs character identity modes.
- Character management and character-mode controls.
- Character avatar support, including Live2D model thumbnails/runtime controls.
- Live2D zoom and motion controls.
- Character voice assignment/backfill workflows.
- Character/Hermes integration surfaces where enabled.

### Assistant memory

- Dedicated memory-management UI inside Chat.
- Server-side assistant context/memory subsystems supply durable context while the browser manages view state.

### Assistant tools and permissions

Omnix exposes a governed capability registry rather than allowing the model unrestricted host access. The visible tool catalog is projected from the same canonical backend capability registry used by policy/runtime code.

Representative tool families include:

- Governed browser automation and browser evidence capture.
- Workspace/code read, search, edit, write, command, test, Git status/diff, and authoritative run-change-set capabilities for coding tasks.
- Gmail read/draft/send actions; destructive deletion is disabled by default in the canonical capability catalog.
- Google Calendar availability/create/delete actions.
- Google Contacts lookup/resolution.
- GitHub repository and pull-request workflows.
- Web research/search.
- Read-only trading market quotes and related market-data capabilities.
- TP-Link Kasa local smart-home discovery/control when configured.
- Other capability namespaces can be exposed as adapters are enabled.

Each capability carries metadata for execution zone, effect, risk, scope, approval policy, network/credential requirements, confirmation/destructive behavior, provider, auditing, and assistant/Hermes visibility.

Default governance follows the risk of the action: low-risk reads can run automatically; writes/executes or medium-risk actions normally require sensitive-action policy; high-risk/destructive actions require explicit approval. Individual capability definitions can be stricter or disabled.

### Coding and generalized agent runs

Chat can route eligible work into the generalized agent runtime. The runtime is not just a prompt wrapper; it provides execution and acceptance infrastructure:

- Semantic task classification and normalization.
- Chat/DIRECT/WORKFLOW/AGENT routing and chat-to-agent bridging.
- Turn plans, planning contracts, planning review, and active-objective tracking.
- TaskGraph compilation, persistence, runtime scheduling, optimization, revision, and quality checks.
- Isolated/local workspace abstraction and dependency tracking.
- Canonical capability grants and broker policy.
- Pi-backed coding execution with guard/broker/model-provider extensions and trusted engineering/review skills.
- Repository guidance compilation.
- Baseline-relative `RunChangeSet` ownership for the candidate under review.
- Acceptance criteria and candidate-bound test validation.
- Evidence identity/coverage validation and research evidence handling.
- Coding-quality evaluation, independent review orchestration, review runtime, and recovery loops.
- Resource grants, budgets, model-fidelity controls, and process-environment handling.
- Subagents and durable workflow runtime.
- Debug logging and persisted run/repository state.
- Run cards/tool execution views in the browser, including collapsible agent activity and tool-result presentation.

The model may plan and operate tools, but capability policy, workspace scope, acceptance, evidence, review subject, and persistence remain enforced by Omnix.

## RPG — `/rpg`

The RPG workspace is a deterministic simulation with AI used for presentation/interaction rather than as the authoritative game-state store.

### Campaign and session lifecycle

- Create campaign/new-game flows.
- Select and persist the active RPG session.
- Live session summaries and replay/checkpoint inventory.
- Save/load/replay-compatible authoritative state.
- RPG jobs, assets, and reports surfaced alongside the session.

### Player and world workstation

- Player rail with hero summary, stats, survival state, equipment, inventory, and related player data.
- Party/member state.
- World rail with location/world-state information.
- NPC relationships and world events.
- Active objectives/quests.
- Hotbar abilities and loadout tabs.
- Journal, recent events, narrative log, and narrative tabs.
- Story-scene rendering and action composer.

### Combat and interaction

- Encounter/combat surface derived from authoritative session state.
- Structured RPG turn submission.
- Quick actions and dynamic response options.
- Turn/job recovery behavior for foreground submissions.

### Hermes-assisted RPG flows

When Hermes is enabled, the RPG workspace can consume:

- Hermes route decisions and contextual suggestions.
- Suggested quick actions.
- Sequence preview/review.
- Approved-flow execution.
- Execution history and results.
- Review-each-step style assistance modes and sequence job panels.

Hermes assistance does not replace the deterministic RPG state authority.

## Storyteller — `/storyteller`

Storyteller provides long-form generation plus an interactive story library/workbench.

- Provider-backed story generation.
- Title and premise input.
- Writing mode and interactive story mode.
- Draft, continue, rewrite paragraph, expand scene, dialogue polish, and summarize actions.
- Tone presets such as Cozy, Hopeful, Gentle, and Mystery.
- Writing-style presets including lyrical/descriptive, fast-paced, dialogue-heavy, cinematic, and literary.
- Job stages for planning/outline, generation, and story-asset storage.
- Draft/story library with local draft continuity, story assets, and trash handling.
- Chapter/scene outline derivation and chapter selection.
- Scene additions appended to existing stories.
- Word-count and reading-time estimates.
- Suggested interactive story moves.
- Saving/exporting completed text into the shared artifact system.

## Podcast — `/podcast`

Podcast turns a topic/brief and speaker configuration into multi-speaker audio.

- Topic/title, brief, audience, tone/language, and duration controls.
- Duration presets from short previews through hour-long targets.
- Debate, interview, and solo speech formats.
- Speaker profiles with identity, beliefs, personality, speaking style, goals, custom instructions, and voice assignment.
- LLM-generated speaker-tagged scripts with a deterministic/local script-builder fallback.
- Per-speaker voice mapping and speaking-style assignment.
- Per-segment TTS preview generation.
- Producer-plan, performance-script, speaking-turn, mix, and renderer job stages.
- Audio output settings and standard podcast effects such as compression/de-essing.
- WAV chunk stitching for live/final preview workflows.
- Final multi-speaker rendering and shared audio assets.

## Voice Studio / TTS — `/voice`

Voice Studio is the main text-to-speech production surface.

- Single-speaker and multi-speaker scripts.
- Script speaker/segment parsing.
- TTS-capable provider selection.
- Voice-profile browsing, filtering, and preview synthesis.
- Per-speaker voice assignment.
- Per-speaker speaking-style assignment.
- Styles including conversational, calm, enthusiastic, warm, authoritative, and narrator presets.
- Output tuning for stability, similarity, style, speed, pitch, and volume.
- Toggleable Equalizer, Reverb, Compression, De-esser, and Noise Reduction effects.
- Job-backed synthesis on the shared TTS resource class.
- Generated audio assets, result selection, and playback controls.
- Active/recent/failed voice job views.
- Voice-sample upload/record workflows and voice-profile creation controls are also integrated into Voice Studio.

## Voice Cloning — `/voice-cloning`

- Choose a voice-cloning/TTS-capable provider.
- Choose an indexed voice sample/audio asset.
- Name the resulting voice profile.
- Configure language and Draft/Standard/High quality.
- Supply optional reference text.
- Queue a staged profile job: sample ingestion → profile build → preview → stored voice-profile asset.
- Inspect profile-job progress.
- Browse generated voice profiles and use shared audio controls.

## Speech to Text — `/stt`

- Select an STT-capable provider.
- Transcribe an indexed audio/voice-sample asset or an external source path.
- Configure language or leave provider-specific automatic behavior.
- Queue shared `stt.transcribe` work on the STT resource class.
- Inspect job progress/resource ownership.
- Browse transcript assets created by completed work.
- Settings-driven default provider/language integration.

## Image Generation — `/image-generation`

The image workspace explicitly separates a lightweight service process from heavyweight model residency.

- Discover supported image providers/models.
- Select a local image model; the current default provider key is `flux_klein`.
- Inspect model download/completeness/load state.
- Download model files, optionally supplying a Hugging Face token where required.
- Explicitly load model weights into memory.
- Explicitly unload weights to release GPU memory.
- Inspect provider and image-worker readiness.
- Generate image jobs only when service/model readiness permits it.
- Shared image-job stages: generation and asset storage.
- Live job updates over the shared event stream.
- Cancel and retry image jobs.
- Latest-result presentation and generated-image gallery.
- Settings-driven image defaults.

The intended flow shown in the UI is: select model → download if needed → load explicitly → generate.

## Trading — `/trading`

Trading is a research, charting, strategy, replay, alerting, and paper-simulation workstation. It is deliberately separated from unrestricted broker mutation authority.

### Chart workspace

- Multiple chart tabs and multiple charts per tab.
- Auto grid or fixed 1–4 column layouts.
- Active-chart management and focus mode.
- Persisted workspace state and downloadable workspace export.
- Canonical instruments and provider bindings/provenance.
- Provider-specific supported interval enforcement.
- Stock and crypto instruments with preferred venue handling.
- Arithmetic/formula symbols that resolve multiple instrument operands.
- Chart-type menu and interval menu.

### Analysis tools

- Core indicator manager and per-chart indicator configuration.
- Drawing tools with snap modes.
- Linked chart/panel behavior.
- Watchlists/favorites.
- Alerts and alert toast navigation back to the matching instrument, interval, binding, and indicator.
- Scanner panel.
- Replay panel.
- Strategy/backtest panel.
- Tool-panel fullscreen mode.

### Trading backend capabilities

The trading backend includes dedicated APIs/services for market data, metrics, alerts, scanning, model/strategy information, replay, catalyst/research data, execution simulation, and related research workflows. The UI includes a dedicated Trade tab for paper-account/paper-order interaction where configured.

Omnix trading research can use shared AI/Hermes research paths, but deterministic strategy/execution policy and paper-trading state remain separate from LLM authority.

## Providers — `/providers`

- Shared provider registry used by all feature modules.
- Provider source/family, health/status, capabilities, latency metadata, and last-error summaries.
- Provider refresh jobs.
- Local and remote/OpenAI-compatible provider abstractions.
- Examples in the codebase include LM Studio, llama.cpp, remote providers, speech/image services, and capability-specific adapters.

## Models — `/models`

- Shared discovered model inventory.
- Provider association and local/remote location.
- Capability mapping.
- VRAM/resource hints where available.
- Default-use metadata.
- Model refresh/discovery jobs.
- Settings and runtime policy for routing/residency live in the Settings subsystem.

## Jobs / Runs — `/jobs`

All long-running feature work converges on a shared job/run model.

- Module/type identity.
- Queue and execution status.
- Resource class/lock such as CPU, LLM GPU, TTS GPU, STT GPU, or image GPU.
- Stage-by-stage status.
- Current/total progress and status message.
- Logs and output references.
- Live event-stream connection status.
- Cancellation of active jobs.
- Feature-specific pages can present filtered views of the same underlying queue.

## Assets — `/assets`

The shared asset system indexes generated or ingested artifacts rather than letting each feature invent a separate output store.

Common asset types include:

- Audio and voice samples.
- Voice profiles.
- Images.
- Transcripts.
- Stories/exports.
- Reports.
- Checkpoints/replay material.
- Other generated documents/artifacts.

Assets carry module/type, MIME type, storage path, metadata, creation information, and feature-specific references. Text assets can be read through guarded gateway content routes; large/non-text content remains file/media oriented.

## Reports — `/reports`

- Shared generated report inventory.
- Report kind, path, and size metadata.
- Used by RPG/autoplay evidence, diagnostics/export workflows, agent/research outputs, and other generated-document flows.

## Settings — `/settings`

Settings is a searchable control center with category navigation and a status rail.

Implemented categories are:

1. Overview — global defaults and whole-system health.
2. Appearance & Accessibility — appearance mode, theme palette, text size, density/motion/caption/accessibility preferences.
3. AI Providers — default provider families, configuration summaries, and connection testing.
4. Trading & Market Data — market-data credentials and chart/research data integrations.
5. Models & Runtime — model discovery, routing, residency, and runtime policy.
6. Assistant & Chat — personality, voice/live chat, web research, and session defaults.
7. Voice & Audio — TTS, cloning, playback, and output tuning.
8. Storyteller & Podcast — writing, reading, narration, and podcast defaults.
9. RPG — campaign defaults, systems, AI presentation, and Hermes assistance.
10. Images & Speech Input — image-generation and STT defaults.
11. Tools & Integrations — capability/tool governance, connections, and Hermes.
12. Jobs, Assets & Storage — operational defaults, retention, asset/storage policy.
13. Diagnostics & Developer — runtime health, logs, tests, and developer diagnostics.

The settings registry records each setting's scope, persistence owner, writeability, application timing, and restart requirement. Browser-only appearance settings remain local; environment/status settings are read-only when runtime-owned.

## Diagnostics — `/diagnostics`

- Gateway/runtime health.
- Worker/service status.
- Provider/model diagnostics.
- Event-stream connection state.
- Job/runtime troubleshooting information.
- Logs/diagnostic exports where available.
- Compatibility status for migrated vs legacy backend surfaces.

## Shared research

Omnix includes provider-neutral web-research capability used by assistant/agent workflows.

- Configurable research default mode, including disabled, quick-search, and deep-research style workflows.
- Primary research provider plus fallback priority.
- Research budgets for queries/sources/extracts/steps.
- Runtime provider/status reporting.
- Source-grounded research results are passed through evidence/coverage validation in agent workflows where required.

## Hermes sidecar

Hermes Agent is optional and runs out of process.

- It can participate in assistant and RPG planning/proposal workflows when enabled.
- Omnix keeps capability/policy authority and application state in Omnix rather than importing Hermes as an unrestricted in-process dependency.
- The Windows launcher can auto-start Hermes when configured.
- See [HERMES_SIDECAR_SETUP.md](HERMES_SIDECAR_SETUP.md).

## Local smart-home support

The backend includes governed TP-Link Kasa/Tapo local-network support.

- Local discovery.
- Device inspection/status.
- Approved device control through the assistant capability system.
- Host/alias can be pinned; discovery can be used when configured.
- Capability policy still applies to device mutation.

This is an integration capability rather than a separate top-level workspace.

## Desktop companion and live-speech subsystems

The source tree also contains desktop-companion and live-speech runtime components used by assistant/live-conversation experiences. These are supporting subsystems rather than separate routed browser modules. Their behavior should be documented under the user-facing Chat/Voice experience unless they become independent application surfaces.

## Feature ownership rule

A feature-specific UI may specialize presentation, but it must not fork the platform infrastructure. New work should reuse:

- the shared web shell and design system;
- typed gateway/API contracts;
- the provider/model registry;
- jobs/runs for long-running work;
- assets/artifacts for generated outputs;
- shared SSE/WebSocket infrastructure;
- settings and diagnostics;
- capability policy for tools/agents;
- backend-owned authoritative domain state.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [DEVELOPMENT.md](DEVELOPMENT.md) for the corresponding implementation rules.
