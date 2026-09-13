# Omnix Feature Catalog

This document catalogs the implemented Omnix application surface. It covers routed workspaces as well as important capabilities embedded inside Chat, Settings, the shared platform layer, and the generalized agent runtime.

A feature can be implemented even when it is not a top-level route. Conversely, configuration or backend compatibility code is not described here as a user-facing feature unless the current application exposes or consumes it.

## App overview

The primary mode switcher exposes Chat, RPG, Storyteller, Podcast, Voice Studio, Image Generation, and Trading. The live conversation surface is part of the Chat experience and can open as an immersive/fullscreen room. Platform workspaces such as Jobs, Assets, Providers, Models, Settings, Reports, and Diagnostics support every mode.

| App or surface | Route | Status | Primary purpose | Screenshot |
| --- | --- | --- | --- | --- |
| Chat and Assistant | `/chatbot` | Implemented | Conversations, tools, memory, attachments, and agent runs | [Chat](images/chat.png) |
| Live Chat | `/chatbot` live/fullscreen surface | Active subsystem | Low-latency text/voice conversation with presence and turn controls | [Live Chat](images/live_chat.png) |
| RPG | `/rpg` | Work in progress | Deterministic campaigns, world state, turns, replay, and authoring | [RPG](images/rpg.png) |
| Storyteller | `/storyteller` | Implemented and evolving | Long-form stories, chapters, interactive moves, narration, and exports | Not yet available |
| Podcast | `/podcast` | Implemented | Multi-speaker script production, TTS preview, mixing, and final render | [Podcast](images/podcast.png) |
| Voice Studio | `/voice` | Implemented | Voice profiles, TTS scripts, tuning, effects, jobs, and playback | [Voice Studio](images/voice_studio.png) |
| Image Generation | `/image-generation` | Implemented | Model residency, generation jobs, galleries, and asset management | [Image Generation](images/image_generation.png) |
| Trading | `/trading` | Research and paper trading | Charts, indicators, alerts, replay, strategies, and paper execution | [Trading](images/trading.png) |

Status labels describe the product surface, not the maturity of every underlying provider. A route can be usable while an optional worker, model, integration, or authoring workflow remains environment-dependent or under active development.

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

![Chat and Assistant workspace](images/chat.png)

The normal Chat path is: choose a session and identity, select a provider/model, send a text or voice turn, watch the streamed response, inspect tool/job activity, and keep any durable result as a shared asset, report, or session message. The browser manages presentation and drafts; session state, jobs, tool authority, and generated outputs remain backend-owned.

### Recommended Chat workflow

1. Start or resume a session and choose System or Character mode.
2. Confirm the selected provider/model and any voice or research defaults.
3. Send a prompt, paste supported image/text context, or open the live conversation surface.
4. Watch the response, tool calls, job progress, and interruption state in the activity area.
5. Review citations, artifacts, reports, or proposed actions before using them downstream.
6. Save durable outputs through the shared asset/report/session surfaces rather than browser-only storage.

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

## Live Chat and live conversation — `/chatbot` live surfaces

![Live Chat workspace](images/live_chat.png)

Live Chat is the immersive conversation surface attached to Chat. It presents a live room, character/presence state, private transcript, microphone and voice controls, and a message fallback in one fullscreen-capable workspace. It is not a separate top-level route; it is a Chat subsystem with its own realtime session and diagnostics concerns.

### Live conversation workflow

1. Open Live Chat from the Chat workspace and confirm the selected character, voice, and conversation settings.
2. Start the call or use text input when the microphone or speech services are unavailable.
3. Speak or send a message; the live session coordinates input capture, turn context, assistant output, and playback.
4. Interrupt naturally when needed. The client tracks barge-in, output cancellation, transcript ordering, and pending speech.
5. End or recover the call, then inspect the session summary, diagnostics, and any durable audio/transcript artifacts.

### Live Chat boundaries

- The browser owns microphone permission, device selection, fullscreen/presence presentation, transcript scrolling, and playback controls.
- The live session coordinator owns turn sequencing, accepted-final routing, interruption state, timing, and delivery ledgers.
- STT/TTS providers and WebSocket/realtime transports are optional service boundaries; their health does not by itself prove that a complete conversation turn is ready.
- Live output remains subject to the same provider, settings, capability, session, and persistence boundaries as ordinary Chat.
- Use the live diagnostics surfaces when calls are silent, duplicated, delayed, or stuck rather than creating an independent polling loop.

## RPG — `/rpg` (work in progress)

The RPG workspace is a deterministic simulation with AI used for presentation/interaction rather than as the authoritative game-state store.

![RPG workspace](images/rpg.png)

> **Work in progress:** the RPG route is actively expanding. The deterministic session, structured turn flow, persistence/replay projections, world/campaign surfaces, and authoring tools are present, while content completeness, generated artwork, and some world-enrichment/editor workflows continue to evolve. Treat placeholder presentation or optional generated media as non-authoritative until the corresponding backend state is accepted.

### First-session workflow

1. Create or select a world/campaign and confirm the active session.
2. Review the hero, party, location, world state, objectives, and available actions.
3. Submit a structured turn from the action composer or choose a quick action.
4. Wait for the authoritative turn result; do not infer state from model narration alone.
5. Inspect the narrative readout, combat/interaction panels, journal, replay/checkpoint state, and any generated report.
6. Use Hermes suggestions only as reviewed proposals; deterministic RPG state remains authoritative.

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

Storyteller is the long-form writing workbench. It combines a local draft editor with server-backed generation actions and a story library, so a writer can move between ideation, revision, chapter organization, reading, narration, and export without treating the browser draft as the only copy.

There is no dedicated Storyteller screenshot in `docs/images` yet; the route is still documented here as a first-class app and can reuse the shared asset/report conventions described below.

### Storyteller workflow

1. Enter a title and premise, choose a writing mode, tone, and style, then create or resume a story.
2. Generate or edit a draft and let the workspace derive chapters/scenes from the document.
3. Use targeted actions such as continue, rewrite paragraph, expand scene, dialogue polish, and summarize.
4. Select a chapter or scene, review the story document, and keep local draft continuity while the server stores durable story assets.
5. Add suggested interactive moves when the story is in interactive mode.
6. Optionally assign a cast/voice, generate chapter or story audio, and export the completed text or media through shared assets.

### Story state and outputs

- The story document, chapters, scenes, and saved assets are the durable content model.
- Local draft state improves editing continuity but does not replace the server copy.
- Generation is job-backed when it may take time; progress and failures should be read from the shared job/event surfaces.
- Reading, audio, attribution, and chapter-media panels are presentation layers over the story document and its referenced assets.

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

![Podcast production workspace](images/podcast.png)

Podcast is a production pipeline rather than a single text-generation request. The workspace keeps episode configuration, participant identities, voice assignment, script state, preview audio, and final rendering visible as one staged run.

### Podcast workflow

1. Define the episode topic, brief, audience, duration, language, tone, and format.
2. Configure the host/guest or solo participants with beliefs, personality, speaking style, goals, instructions, and voices.
3. Generate or review the speaker-tagged script before requesting live or final audio.
4. Follow the staged production path: producer plan → performance script → speaking turns → mix → renderer.
5. Preview segments, inspect progress/logs, and recover or retry individual jobs when supported.
6. Keep the final multi-speaker render as a shared audio asset for playback and download.

### Podcast authority and failure boundaries

- The script builder may provide a deterministic/local fallback, but it does not bypass provider selection or job persistence.
- Voice assignment and TTS readiness are separate from script generation readiness.
- Live preview chunks and the final render are different outputs; do not treat an incomplete preview as the final episode.
- Audio effects and mixing are production controls; they do not change the source script or speaker identity metadata.

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

![Voice Studio workspace](images/voice_studio.png)

Voice Studio is the main TTS production surface. It separates reusable voice identity from each synthesis job: profiles live in the voice library, scripts describe the requested content, and jobs produce audio assets with playback and recovery state.

### Voice Studio workflow

1. Choose a single-speaker or multi-speaker script and normalize its speaker/segment structure.
2. Search the voice library, preview candidates, and assign one voice plus a speaking style per speaker.
3. Tune stability, similarity, style, speed, pitch, volume, and optional effects for the requested output.
4. Submit the synthesis job and observe its TTS resource class, stages, progress, logs, and result references.
5. Play the selected output, compare recent/failed jobs, and retry or recover without losing the source script.
6. Keep successful audio in the shared asset system so Podcast, Storyteller, Chat, and downstream export workflows can reuse it.

### Voice readiness checklist

- A voice profile/sample exists and is readable by the selected provider.
- The provider advertises TTS capability and reports healthy/readiness state.
- The script has valid speaker labels and non-empty segments.
- The TTS worker is reachable and has the resources needed for the selected model.
- Output settings are compatible with the provider; service health alone does not guarantee synthesis readiness.

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

![Image Generation workspace](images/image_generation.png)

Image Generation exposes model residency as an explicit operational state. A running image service can still have no model loaded, and the generate action is intentionally blocked until the selected model is complete, loaded, and ready for the worker.

### Image Generation workflow

1. Inspect provider/model discovery and select an image-capable model.
2. Check download completeness, load state, worker health, and available resource/VRAM hints.
3. Download missing model files when permitted, then explicitly load the weights.
4. Add a prompt and optional reference images, choose output settings, and submit a shared image job.
5. Watch generation and asset-storage stages through the event stream; cancel or retry when the job policy allows it.
6. Open the latest result or Image Assets gallery and keep the generated file with its prompt/provider/model metadata.

### Image safety and recovery notes

- Hugging Face or other provider credentials must remain in protected environment/configuration storage.
- Unload heavyweight models when reclaiming GPU memory; a healthy process does not imply resident weights.
- Reference-conditioned requests may have different caching behavior from reusable text-only requests.
- A failed generation should be diagnosed at the model, worker, provider, resource, and asset-storage boundaries in that order.

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

![Trading workspace](images/trading.png)

Trading is a research and paper-simulation terminal. It can display live or replayed market data, calculate indicators, annotate charts, compare instruments, and evaluate strategies, but AI/Hermes analysis is not a grant of broker execution authority.

### Trading workflow

1. Choose an instrument and provider binding, then confirm the supported interval and data source.
2. Open one or more chart tabs, select the layout, and configure chart type, overlays, indicators, and drawings.
3. Add watchlist symbols, alerts, comparisons, scanner criteria, or research context as needed.
4. Use replay and backtest tools to test a hypothesis against historical data before considering paper execution.
5. Review automated analysis as research with its source/provenance and confidence context.
6. Use the Trade/paper surface only with an explicitly configured paper account; inspect orders, positions, fills, and risk controls before submitting.

### Trading data and authority boundaries

- Market data providers own quote/bar freshness and capability metadata; the chart should expose provenance rather than silently mixing sources.
- Workspace persistence stores chart tabs, layouts, indicators, drawings, bindings, and alert context for recovery/export.
- Alerts and research can navigate back to the exact symbol, interval, chart, and provider binding that produced them.
- Paper-account state and simulated fills are backend-owned; browser state is presentation and intent only.
- AI/Hermes output remains analysis or a proposal until a deterministic strategy/runtime explicitly owns execution authority.

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
