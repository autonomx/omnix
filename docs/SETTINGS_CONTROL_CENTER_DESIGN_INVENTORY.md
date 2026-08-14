# Omnix Settings Control Center

## Feature inventory and image brief

**Prepared:** 2026-07-05  
**Target:** `src/apps/web` `/settings` on the `rpg` branch

## Goal

The current Settings page exposes Hermes status plus three writable provider defaults, while many real controls live inside Chatbot, Voice Studio, Storyteller, Podcast, RPG, STT, Image Generation, and Assistant Tools.

The redesign should make `/settings` a central control center for app-wide and module defaults while preserving per-session and per-job overrides inside each workspace.

## Setting scopes

Every row should show a scope badge:

- **Global** — app-wide default.
- **Module** — default for one workspace.
- **Session** — chat, story, or RPG campaign value.
- **Job** — one generation, transcription, or render request.
- **Local** — browser-persisted preference.
- **Environment** — service/process configuration.
- **Status** — read-only health or runtime information.

Environment and Status values must not look like ordinary saved preferences.

## Current `/settings` baseline

Confirmed current content:

- Default LLM provider.
- Default TTS provider.
- Default STT provider.
- Provider configuration summaries for LM Studio, OpenRouter, Cerebras, and llama.cpp.
- Image-generation and RPG-visual enablement status.
- Worker URL summaries.
- Hermes state, reachability, setup guidance, health/capabilities, refresh, dry-run test, review, and recent activity.

The current gateway settings payload contains `provider`, `audio_provider_tts`, `audio_provider_stt`, `image_enabled`, `rpg_visual_enabled`, provider settings, and worker URLs.

## Proposed navigation

Use the existing Omnix application navigation on the far left, then add an inner Settings category rail:

1. Overview
2. Appearance & Accessibility
3. AI Providers
4. Models & Runtime
5. Assistant & Chat
6. Voice & Audio
7. Storyteller & Podcast
8. RPG
9. Images & Speech Input
10. Tools & Integrations
11. Jobs, Assets & Storage
12. Diagnostics & Developer

Include `Search settings…` at the top of the rail.

## Complete feature inventory

### Overview

Editable quick defaults:

- Default LLM provider.
- Default chat model.
- Default TTS provider.
- Default STT provider.
- Default image provider.
- Default assistant voice.
- Default assistant personality.

Status summary:

- Gateway and event stream.
- Provider availability.
- Loaded models and VRAM hints.
- TTS, STT, image worker, and Hermes.
- Active and queued jobs.
- Asset/library summary.

### Appearance & Accessibility

Existing assistant preference contract:

- Appearance: System, Light, Dark.
- Density: Comfortable, Compact.
- Reduce motion.
- Live captions.
- Default assistant ID.

Good future additions, clearly marked Planned until implemented:

- UI scale.
- Remember sidebar state.
- High-contrast status indicators.
- Descriptive labels beside icons.
- Confirm destructive actions.

### AI Providers

Global defaults:

- LLM provider: LM Studio, OpenRouter, Cerebras, llama.cpp, and discovered providers.
- TTS provider: Faster Qwen3 TTS and discovered TTS providers.
- STT provider: Parakeet STT and discovered STT providers.
- Image provider.
- Voice-cloning provider.

Provider cards should show:

- Enabled/configured state.
- Endpoint summary.
- Default model.
- Connection status and last error.
- Latency summary.
- Capabilities: Chat, Completion, TTS, STT, Image, Voice cloning, Diagnostics, Model discovery.
- Test connection and Configure actions.

Sensitive values must remain masked and must not appear in logs or the concept image.

### Models & Runtime

- Refresh installed and remote models.
- Filter by provider, location, and capability.
- Model path/status for local models.
- VRAM hint.
- Default-for metadata.
- Global chat, fast, quality, background, embedding, image-prompt, and fallback model defaults.
- Advanced RPG task routing for intent, narration, dialogue, combat narration, memory, journal, quality rewrite, grounding audit, and image prompt.
- Read-only model residency and co-residency policy until writable runtime APIs exist.
- Manual unload and idle-unload policy only after a real backend contract is added.

### Assistant & Chat

- Default provider and model.
- Assistant personality presets: Omnix Default, Concise operator, Friendly coach, Technical expert, Creative collaborator, Custom personality.
- Custom personality prompt.
- Default or cloned voice.
- Preview selected voice.
- Auto-speak assistant replies.
- Speech-input language.
- Browser recognition versus configured STT service status.
- Live captions.
- Streaming response audio.
- Barge-in/interruption behavior.
- Voice auto-send delay as an advanced setting.

Current personality and voice preferences are browser-persisted and apply to new sessions/audio.

### Voice & Audio

Existing Voice Studio output controls:

| Control | Default |
|---|---:|
| Stability | 0.75 |
| Similarity | 0.80 |
| Style | 0.35 |
| Speed | 1.00 |
| Pitch | 0 |
| Volume | 0 |

Existing speaking styles:

- Confident, Conversational.
- Calm.
- Enthusiastic.
- Warm.
- Deep, Authoritative.
- Narrator, Clear.

Existing effects:

- Equalizer.
- Reverb.
- Compression.
- De-esser.
- Noise Reduction.

Also centralize module defaults for:

- TTS provider, voice, language, output behavior, and streaming mode.
- Speaker-role voice/style assignments.
- Voice cloning provider, source type, sample asset, profile name, language, quality, reference text, and notes.

Voice Studio retains per-job overrides.

### Storyteller & Podcast

Storyteller controls:

- Provider.
- Tone: Cozy, Hopeful, Gentle, Mystery.
- Writing style: Lyrical & Descriptive, Fast-paced, Dialogue-heavy, Cinematic, Literary.
- Actions: Draft, Continue, Rewrite, Expand, Dialogue polish, Summarize.
- Default chapter behavior and save/export defaults.

Story reading preferences:

| Setting | Default |
|---|---:|
| Pronunciation dictionary | Empty |
| Pause after paragraph | 500 ms |
| Pause after chapter | 1,200 ms |
| Read chapter titles | On |
| Speed | 1.00 |
| Style preset | Dramatic audiobook |

Podcast controls:

- Format: Debate, Interview, Speech.
- Duration: 2, 5, 10, 15, 20, 30, 45, or 60 minutes.
- Tone: Professional, Conversational, Humorous.
- Language: English US or UK.
- Generation style: Automatic or Guided.
- Audience.
- Participant identity, beliefs, personality, speaking style, goal, instructions, and voice.
- Playback rate and autoplay.
- Current audio defaults: speed 1, pitch 0, stability 0.72, similarity 0.78, Compression, De-esser.

### RPG

Preferred campaign defaults should be stored centrally but remain overridable in the campaign wizard:

- Character name and pronouns.
- Background and build.
- Primary and secondary capabilities.
- Power source and origin.
- Motivation, target, flaw, and values.
- Starting location.
- Opening hook and pace.
- Relationship preset.
- Deterministic seed.
- Point-buy stats.

World and difficulty:

- Difficulty: Story, Normal, Harsh.
- World activity: Quiet, Standard, Living world.
- Economy pressure: Relaxed, Normal, Strict.
- Combat lethality: Safe, Normal, Deadly.
- Companions.
- Permadeath.

Existing system toggles:

- Autosave.
- Grounding validator.
- Background soft audit.
- LLM narration.
- Image generation.
- TTS.
- STT.

Advanced candidates, marked Planned until implemented:

- Interaction persistence.
- Deferred narration.
- Background-audit state-update permission.
- Compact context/token budget.
- Loop detection.
- Suggested actions.
- Journal/recap cadence.
- Image/TTS automation modes.

Hermes RPG assistance:

- Off, Suggestions only, Review each step, Approved flow.
- Require approval before state-changing actions.
- Maximum planned steps.
- Show route diagnostics.
- Retain execution history.

### Images & Speech Input

Image generation controls:

- Provider.
- Default width and height: 768 × 768.
- Minimum dimension 128, step 64.
- Default aspect ratio.
- Image and RPG-visual enablement status.
- Portrait and scene presets.
- Keep loaded versus unload after generation.

STT controls:

- Provider.
- Audio asset or external path.
- Language or automatic detection.
- Alignment.
- Save transcript asset.
- Microphone device and supported browser audio processing.

### Tools & Integrations

Assistant tools already support:

- Per-tool enable/disable.
- Connect, disconnect, and test account.
- Connected-account summary.
- Per-action enable/disable.
- Approval policy: Allow automatic, Ask for sensitive, Always ask, Disabled.
- Risk, destructive-action, and confirmation indicators.
- OAuth app configuration for supported integrations.
- Execution-panel access.

Hermes grouping:

1. Connection — state, endpoint summary, test, refresh.
2. Setup — required commands and environment guidance.
3. Behavior — module enablement and approval defaults.
4. Review — proposed actions and recent execution history.

### Jobs, Assets & Storage

Current operations:

- Queue, status, progress, resource lock, stages, logs, cancel, live events.
- Audio, image, voice, transcript, story, report, checkpoint, and export assets.

Future settings after backend support:

- Concurrency by resource class.
- Retry policy.
- Job-history retention.
- Temporary-asset cleanup.
- Default save-output behavior by module.
- Asset retention and re-indexing.

Architecture policy should remain read-only:

- Browser access to workers is forbidden.
- Gateway access to workers is required.
- Generated media should return asset references.
- Base64 media is transitional only.
- Small JSON payloads are allowed.

### Diagnostics & Developer

- Gateway and worker health.
- Event-stream state, reconnect attempt, and retry delay.
- Provider/model cache.
- Model residency and co-residency.
- Worker URLs.
- Sanitized logs and recent provider errors.
- Run all tests.
- Refresh providers/models.
- Copy or download sanitized diagnostics.
- Raw metadata and feature-flag sources only in Developer mode.

Never expose secrets, authorization headers, or embedded media payloads.

## Interaction requirements

- Search by label, provider/model name, synonym, and category.
- Show scope badges on every editable group.
- Sticky `Save changes`, `Discard`, and unsaved-change count.
- Explain whether changes affect new sessions/jobs only.
- Explain when a restart is required.
- Keep advanced settings collapsed by default.
- Use status chips: Ready, Connected, Degraded, Offline, Missing configuration, Restart required.
- Put destructive data actions in a separate Danger Zone with confirmation.

## Recommended desktop layout

- Existing Omnix navigation at far left.
- Settings category rail around 240 px.
- Main form column around 760–840 px.
- Sticky right status column around 300 px.
- Header with breadcrumb, title, search, unsaved count, Discard, and Save changes.
- Group related controls into cards; avoid one giant form.
- At narrower widths, move status below the form and collapse the category rail into a drawer.

## Primary image concept

Generate the first mockup with **AI Providers** selected.

Visible main content:

1. **Default providers** — LM Studio, Qwen3.6 27B, Faster Qwen3 TTS, Parakeet STT, FLUX.2 local.
2. **LM Studio** — Connected status, local endpoint summary, current model, capability chips, Test connection, Configure.
3. **Remote providers** — OpenRouter Missing configuration, Cerebras Configured, llama.cpp Offline.
4. **Routing & fallback** — Fast, Quality, Background, Fallback, and collapsed Advanced task routing.

Right status column:

- Gateway Ready.
- LM Studio Connected.
- TTS Ready.
- STT Ready.
- Image worker Idle.
- Hermes Disabled.
- Subtle GPU memory meter.
- One active job.
- Run all tests.

## Image-generation prompt

> High-fidelity desktop web app UI mockup for an AI creation platform named Omnix, showing a sophisticated dark-mode Settings Control Center at 1600 by 1000. Preserve a narrow far-left Omnix app navigation, then add a dedicated settings category rail with AI Providers selected. Header includes breadcrumb Omnix / Settings, title Settings Control Center, wide Search settings input, 3 unsaved changes, Discard, and bright Save changes. Main content uses clean grouped cards: Default providers with LM Studio, Qwen3.6 27B, Faster Qwen3 TTS, Parakeet STT, and FLUX.2 local; an LM Studio connection card with Connected status, local endpoint summary, capability chips, Test connection and Configure; remote provider rows for OpenRouter, Cerebras, and llama.cpp; Routing & fallback with Fast, Quality, Background, Fallback, and collapsed Advanced task routing. Sticky right System status column shows Gateway Ready, LM Studio Connected, TTS Ready, STT Ready, Image worker Idle, Hermes Disabled, subtle GPU memory meter, one active job, and Run all tests. Premium developer-tool visual language, deep charcoal and midnight navy surfaces, restrained cyan-blue primary accent, small violet highlights, soft one-pixel borders, subtle shadows, rounded 10 to 12 pixel cards, compact readable spacing, polished status chips, realistic dropdowns and toggles, no giant empty areas, no mobile layout, no marketing illustration, no visible secrets, no placeholder text, no excessive neon or glassmorphism.

## Image acceptance checklist

- Existing Omnix navigation remains visible.
- Settings has its own category rail.
- Selected category is obvious.
- Search, save, discard, and unsaved state are visible.
- Status is separated from editable controls.
- Global defaults and module overrides are conceptually distinct.
- No sensitive value appears in plain text.
- Advanced settings are discoverable but collapsed.
- Layout is dense, readable, and consistent with the dark Omnix shell.
- Labels use real Omnix concepts rather than generic placeholders.

## Source map

- `src/apps/web/src/app/modules.ts`
- `src/apps/web/src/app/router.tsx`
- `src/apps/web/src/features/platform/SettingsWorkspace.tsx`
- `src/apps/web/src/features/platform/PlatformModuleWorkspace.tsx`
- `src/apps/web/src/features/platform/HermesStatusCard.tsx`
- `src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx`
- `src/apps/web/src/features/chatbot/AssistantToolSettingsPanel.tsx`
- `src/apps/web/src/features/assistant-workspace/preferences.ts`
- `src/apps/web/src/features/voice/VoiceWorkspace.tsx`
- `src/apps/web/src/features/voice/outputDefaults.ts`
- `src/apps/web/src/features/voice-cloning/VoiceCloningWorkspace.tsx`
- `src/apps/web/src/features/storyteller/StorytellerWorkspace.tsx`
- `src/apps/web/src/features/storyteller/storyReadSettings.ts`
- `src/apps/web/src/features/podcast/PodcastWorkspace.tsx`
- `src/apps/web/src/features/rpg/RpgWorkspace.tsx`
- `src/apps/web/src/features/rpg/RpgCreateCampaignWizard.tsx`
- `src/apps/web/src/features/image-generation/ImageGenerationWorkspace.tsx`
- `src/apps/web/src/features/stt/SttWorkspace.tsx`
- `src/apps/web/src/api/client.ts`
- `src/apps/web/src/api/generated/types.ts`

Update this document whenever Omnix adds a user-facing preference, provider capability, module default, integration policy, or operational control.