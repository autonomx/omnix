# Omnix Settings Control Center Implementation Roadmap

**Target branch:** `rpg`  
**Companion design inventory:** `docs/SETTINGS_CONTROL_CENTER_DESIGN_INVENTORY.md`  
**Target route:** `/settings`

## Objective

Replace the current sparse Settings workspace with the unified Settings Control Center shown in the approved mockup, without creating duplicate configuration state or breaking existing module workflows.

The implementation must centralize app-wide and module defaults while keeping session-specific and job-specific overrides in Chatbot, Voice Studio, Storyteller, Podcast, RPG, Image Generation, and STT.

## Current baseline

The current implementation has four important constraints:

1. `SettingsWorkspace.tsx` composes Hermes cards with the generic platform Settings view.
2. `PlatformModuleWorkspace.tsx` owns the current editable provider form and only saves LLM, TTS, and STT provider IDs.
3. `SettingsPayload.settings` and `saveSettings()` are loosely typed, so the frontend cannot safely support a large form with field validation, migration, dirty-state tracking, or conflict handling.
4. Real preferences are distributed across backend settings, browser storage, environment configuration, module state, session state, and one-off job payloads.

The roadmap therefore starts with contracts and persistence before expanding the visual surface.

## Delivery principles

- One narrow, auditable PR per slice.
- Preserve deterministic RPG boundaries and existing required CI gates.
- Do not move per-job content fields into global Settings.
- Do not make environment or health fields look editable.
- Do not expose stored secrets, authorization values, or raw media payloads.
- Prefer pure helpers, typed contracts, adapters, repositories, and reusable form primitives.
- Keep backward compatibility for current `/api/settings` consumers during migration.
- Mark unsupported controls as `Planned`; do not render fake working controls.
- Each module adopts central defaults only after its current behavior is covered by regression tests.

## Target architecture

### Settings document

Introduce a versioned settings document with explicit namespaces:

```text
schema_version
revision
global
  providers
  models
  routing
appearance
assistant
voice
storyteller
podcast
rpg
image
stt
storage
```

Tool governance should continue using its existing dedicated configuration endpoint unless a later adapter provides a read-only summary in the central document.

Runtime health, worker URLs, Hermes reachability, loaded-model residency, and job state should remain separate status queries rather than persisted preference fields.

### Field metadata

The frontend registry should describe each setting with:

- stable key
- category and section
- label and help text
- value type and allowed values
- default value
- scope: Global, Module, Session, Job, Local, Environment, or Status
- persistence owner
- whether a restart is required
- whether the change applies only to new sessions or jobs
- search aliases
- validation rule
- feature availability

### Save behavior

Evolve the current settings API without breaking the existing provider-only request:

- GET returns the typed effective settings document, revision, and safe configuration metadata.
- POST accepts a typed patch plus the caller's base revision.
- Existing provider-only POST bodies remain accepted through a compatibility adapter.
- Validation errors identify individual field paths.
- Revision conflicts return the latest revision instead of silently overwriting another edit.
- Sensitive configuration is represented only by safe state such as `configured`, `missing`, or `restart_required`.

## Milestones

### MVP milestone

Phases SCC-0 through SCC-5 deliver the first production-usable Control Center:

- typed contracts and persistence
- new Settings shell
- AI Providers screen matching the mockup
- system status column
- search, dirty state, discard, save, and validation

### Full centralization milestone

Phases SCC-6 through SCC-14 migrate module defaults and operational views into the Control Center.

### Launch milestone

Phase SCC-15 completes accessibility, responsive behavior, performance, migration cleanup, and release gating.

---

## Phase SCC-0 — Foundation and ownership map

### SCC-0.1 — Settings registry contract

Create pure frontend contracts for:

- category definitions
- setting definitions
- scope badges
- persistence owners
- availability states
- restart and applies-to metadata

Suggested location:

- `src/apps/web/src/features/settings/settingsRegistry.ts`
- `src/apps/web/src/features/settings/settingsTypes.ts`

Acceptance:

- Every setting in the design inventory can be represented without a UI component.
- Duplicate keys and invalid category references fail tests.
- Environment and Status entries cannot be registered as writable fields.

### SCC-0.2 — Existing-source ownership map

Add a source map that identifies which current setting is owned by:

- `/api/settings`
- browser storage
- module/session state
- job payload
- integration-specific API
- runtime status API

Acceptance:

- No setting is scheduled for migration without a named current owner and target owner.
- Per-job controls are explicitly excluded from global persistence.

### SCC-0.3 — Shared defaults and merge helpers

Add pure helpers for:

- default document creation
- deep merge with known-key filtering
- namespace extraction
- effective module settings
- schema-version migration

Acceptance:

- Unknown or malformed values cannot corrupt defaults.
- Migration output is deterministic.
- Existing provider defaults are preserved.

---

## Phase SCC-1 — Typed backend settings profile

### SCC-1.1 — OpenAPI schemas

Replace the loose settings request/response shapes with typed schemas for:

- settings document
- settings patch request
- settings save response
- field validation errors
- revision conflict response
- safe provider configuration metadata

Regenerate `src/apps/web/src/api/generated/types.ts`.

Acceptance:

- `SettingsPayload.settings` is no longer the primary untyped contract.
- Generated frontend types expose all implemented namespaces.
- Existing fields remain available during compatibility migration.

### SCC-1.2 — Settings repository and persistence

Add a repository/service behind `/api/settings` that owns:

- versioned document loading
- atomic writes
- default merge
- schema migration
- revision generation
- preservation of unrelated supported values

Acceptance:

- A failed write does not leave a partial document.
- Restarting the backend preserves saved values.
- Old provider-only configuration is migrated without loss.
- Unknown unsafe fields are rejected or ignored according to the documented policy.

### SCC-1.3 — Compatibility route adapter

Keep current GET/POST behavior working while routing through the new repository.

Acceptance:

- The current Settings page can still load and save provider defaults.
- Existing API regression tests continue to pass.
- Compatibility behavior is documented and has a removal phase.

### SCC-1.4 — Backend validation and redaction

Add field-level validation and safe response serialization.

Acceptance:

- Invalid provider/model relationships return a field error.
- Secrets never appear in settings responses, logs, diagnostics, or tests.
- Revision conflicts do not overwrite newer values.

---

## Phase SCC-2 — Frontend settings data layer

### SCC-2.1 — Typed API client

Update `src/apps/web/src/api/client.ts` with typed methods for:

- load settings profile
- save settings patch
- handle validation errors
- handle revision conflicts

Acceptance:

- No Settings Control Center code sends `Record<string, unknown>`.
- Error types are usable by forms without parsing arbitrary strings.

### SCC-2.2 — Settings draft store

Create a reducer/store with:

- server snapshot
- editable draft
- dirty field paths
- reset/discard
- save-pending state
- per-field errors
- revision-conflict state

Acceptance:

- Editing and reverting a value clears its dirty state.
- Discard restores the last server snapshot.
- A failed save retains the draft.
- A successful save installs the returned canonical document.

### SCC-2.3 — Local preference adapter

Provide one typed adapter for browser-persisted preferences.

Initial targets:

- appearance
- density
- reduced motion
- live captions
- assistant voice/personality until backend migration is complete

Acceptance:

- Existing browser values are imported once.
- Invalid stored JSON falls back safely.
- Central and module views read the same adapter rather than separate storage keys.

---

## Phase SCC-3 — Control Center shell

### SCC-3.1 — Route composition cleanup

Refactor `SettingsWorkspace.tsx` into the dedicated Settings entry point.

- Move the old `SettingsView` out of `PlatformModuleWorkspace.tsx`.
- Keep non-Settings platform modules unchanged.
- Place Hermes content in a temporary adapter until Tools & Integrations lands.

Acceptance:

- `/settings` renders only the new shell.
- Providers, Models, Jobs, Assets, Reports, and Diagnostics routes are unaffected.

### SCC-3.2 — Desktop shell

Implement:

- breadcrumb and title
- Settings category rail
- main content area
- right status column slot
- sticky action header
- responsive collapse points

Suggested components:

- `SettingsControlCenter`
- `SettingsCategoryRail`
- `SettingsHeader`
- `SettingsSection`
- `SettingsStatusRail`
- `SettingScopeBadge`

Acceptance:

- Layout matches the approved mockup at desktop widths.
- Existing Omnix navigation remains unchanged.
- Keyboard focus order is logical.
- The shell works with empty/loading/error states.

### SCC-3.3 — Reusable settings controls

Add consistent wrappers for:

- select
- text field
- number field
- switch
- slider
- segmented choice
- status row
- advanced accordion
- action row

Acceptance:

- Labels, help text, errors, scope, and applies-to metadata are rendered consistently.
- Disabled, read-only, planned, and restart-required states are visually distinct.

---

## Phase SCC-4 — AI Providers vertical slice

This is the first complete page and should visually match the generated mockup.

### SCC-4.1 — Default provider and model card

Implement editable defaults for:

- LLM provider
- chat model
- TTS provider
- STT provider
- image provider when the backend contract is ready

Acceptance:

- Model options filter by selected provider and capability.
- Invalid stale selections are surfaced rather than silently replaced.
- Helper text explains that module workspaces may override defaults.

### SCC-4.2 — Provider summary cards

Render local and remote provider cards from the provider registry:

- status
- source/family
- endpoint summary
- current/default model
- capabilities
- last error
- safe configuration state

Acceptance:

- LM Studio, OpenRouter, Cerebras, and llama.cpp are data-driven, not hard-coded presentation branches.
- No sensitive value is displayed.
- Unknown providers render with a generic card.

### SCC-4.3 — Configure and test flows

Add provider detail drawer or modal with supported non-sensitive fields and connection testing.

Acceptance:

- Test actions do not modify saved defaults.
- Environment-managed fields explain their source and restart requirement.
- Unsupported configuration fields remain read-only.

### SCC-4.4 — Routing and fallback

Implement global routing defaults:

- fast model
- quality model
- background model
- fallback behavior

Keep task-specific routing collapsed under Advanced.

Acceptance:

- Routing values validate against current provider/model capabilities.
- Fallback loops and unavailable-only chains are rejected.

---

## Phase SCC-5 — Status, search, and save UX

### SCC-5.1 — System status rail

Aggregate existing queries for:

- gateway
- LM Studio/provider state
- TTS
- STT
- image worker
- Hermes
- active jobs
- model residency/VRAM summary when available

Acceptance:

- Status data is read-only and refreshable.
- A failed status source does not block editing settings.
- `Run all tests` reports partial failures clearly.

### SCC-5.2 — Settings search

Implement indexed search over registry metadata.

Acceptance:

- Search matches labels, aliases, categories, providers, and models.
- Results identify category and scope.
- Selecting a result navigates and focuses the field.
- Hidden advanced fields can be found without automatically changing values.

### SCC-5.3 — Sticky dirty/save flow

Implement:

- unsaved count
- Save changes
- Discard
- save success/failure
- field errors
- conflict recovery
- before-navigation warning

Acceptance:

- Actions such as Test connection and Refresh do not mark the form dirty.
- Save sends only changed namespaces/fields.
- Conflict UI offers reload or deliberate reapply rather than silent overwrite.

**MVP exit gate:** Phases SCC-0 through SCC-5 are complete, tested, and usable as the production AI Providers settings page.

---

## Phase SCC-6 — Appearance & Accessibility

Implement existing preference-contract fields:

- appearance
- density
- reduce motion
- live captions
- default assistant ID when supported

Then add only implemented accessibility controls from the design inventory.

Acceptance:

- Theme changes apply without reload.
- Reduced motion affects Settings and shared assistant animations.
- Existing browser preferences migrate without resetting users.
- Planned controls are not interactive.

---

## Phase SCC-7 — Assistant & Chat defaults

Migrate shared defaults for:

- provider and model
- personality preset
- custom personality
- voice profile
- auto-speak replies
- live captions
- speech-input language
- streaming audio preference

Update `ChatbotWorkspace.tsx` to consume central defaults while retaining session overrides.

Acceptance:

- Existing local personality and voice values are imported.
- New chat sessions use central defaults.
- Existing sessions retain their own provider/model/system prompt behavior.
- Chat and Settings display the same effective value.

---

## Phase SCC-8 — Voice & Audio defaults

Centralize module defaults for:

- TTS provider
- voice/profile
- language
- stability
- similarity
- style
- speed
- pitch
- volume
- enabled effects
- streaming behavior
- voice-cloning provider/language/quality

Update Voice Studio and voice-cloning forms to initialize from defaults while preserving per-job edits.

Acceptance:

- Changing a job form does not overwrite module defaults.
- Reset-to-default restores central values.
- Existing Voice Studio output behavior remains compatible.
- Numeric ranges are validated in both frontend and backend.

---

## Phase SCC-9 — Storyteller & Podcast defaults

Storyteller:

- provider/model
- tone
- writing style
- title/save/export preferences
- reading pauses, speed, title reading, pronunciation dictionary, style preset

Podcast:

- script provider/model
- format
- duration
- tone
- language
- generation style
- autoplay/playback rate
- default voice/effects/output tuning

Acceptance:

- Existing Story Read local settings migrate correctly.
- Story and Podcast jobs record the effective defaults in their payload metadata.
- Per-story and per-episode changes remain local to the current workflow.

---

## Phase SCC-10 — RPG defaults and advanced routing

### SCC-10.1 — Campaign preference defaults

Centralize preferred starting values for the existing campaign wizard without turning them into authoritative session state.

Acceptance:

- New campaign wizard initializes from preferences.
- Deterministic seed and submitted request are unchanged after the wizard opens.
- Existing campaigns are never mutated by changing preferences.

### SCC-10.2 — RPG system defaults

Centralize existing supported values:

- difficulty
- world activity
- economy pressure
- combat lethality
- companions
- permadeath
- autosave
- validator
- background soft audit
- LLM narration
- image generation
- TTS
- STT

Acceptance:

- New-game request serialization remains deterministic.
- Every value has backend coverage proving it affects only newly created campaigns.

### SCC-10.3 — RPG prompt routing

Expose the existing RPG prompt-profile tasks through Advanced task routing.

Acceptance:

- Registry validation prevents missing providers/models and unsupported capabilities.
- Routing metadata is included in reports/debug output.
- Simulation truth remains independent of LLM presentation choices.

### SCC-10.4 — Hermes assistance defaults

Centralize only settings supported by the existing Hermes APIs:

- assistance enabled
- assist mode
- approval requirement
- diagnostics visibility
- execution-history preference

Acceptance:

- Approved-flow state remains disabled unless its backend feature is enabled.
- Settings never bypass review/approval gates.

---

## Phase SCC-11 — Images & Speech Input

Image defaults:

- provider/model
- width and height
- aspect ratio presets
- portrait/scene presets when implemented
- model keep-loaded or unload preference when writable runtime support exists

STT defaults:

- provider
- language
- alignment
- save transcript
- browser microphone preferences where supported

Acceptance:

- Image and STT job forms initialize from defaults.
- Per-job values remain editable.
- Unsupported provider parameters are hidden rather than sent.

---

## Phase SCC-12 — Tools & Integrations

### SCC-12.1 — Tool summary page

Reuse the existing Assistant Tool configuration API to render:

- tool enablement
- connection state
- enabled action count
- approval-policy summary
- Configure and Test actions

Acceptance:

- No duplicate tool-governance persistence is introduced.
- Existing action-level approval behavior is unchanged.

### SCC-12.2 — Tool detail drawer

Move or reuse detailed action governance and connection controls in the central Settings shell.

Acceptance:

- Enablement and approval updates are immediately reflected in Chatbot Tools.
- Destructive/high-risk actions retain confirmation requirements.

### SCC-12.3 — Hermes integration page

Move Hermes status, setup guidance, review, and recent activity from the top of Settings into Tools & Integrations.

Acceptance:

- Existing dry-run, review, and recent surfaces remain functional.
- Environment-managed setup is clearly read-only.

---

## Phase SCC-13 — Jobs, Assets, Storage, and Diagnostics

Implement read-only operational pages first:

- active/recent jobs
- asset counts by type
- storage paths/policies
- gateway and worker health
- event-stream state
- provider/model cache
- model residency
- sanitized logs

Add writable retention, concurrency, cleanup, or residency policies only after dedicated backend contracts exist.

Acceptance:

- Operational actions are separated from preference saves.
- Cancel, cleanup, or reset actions require appropriate confirmation.
- Diagnostics export is sanitized.

---

## Phase SCC-14 — Cross-workspace adoption and compatibility removal

### SCC-14.1 — Remove duplicate storage readers

After each module has migrated, replace direct local-storage/default constants with the shared settings adapter.

Acceptance:

- One owner exists for each central default.
- Module forms still retain temporary unsaved overrides.

### SCC-14.2 — Remove legacy Settings view

Delete the old provider form and compatibility-only frontend code.

Acceptance:

- No route imports or tests reference the old Settings view.
- `/settings` uses only the Control Center.

### SCC-14.3 — Retire provider-only API compatibility

Remove the compatibility adapter only after all clients use the typed request.

Acceptance:

- API contract version and migration notes are updated.
- Old request rejection is explicit and tested.

---

## Phase SCC-15 — Production polish and launch gate

### Accessibility

- Full keyboard navigation.
- Visible focus states.
- Correct labels, descriptions, errors, and live regions.
- No color-only status meaning.
- Reduced-motion compliance.

### Responsive behavior

- Desktop three-column layout.
- Collapsible Settings rail at medium widths.
- Status rail moves below content at narrower widths.
- No horizontal form clipping.

### Performance

- Lazy-load category panels.
- Reuse provider/model/status queries.
- Avoid rerendering the full page on every field edit.
- Keep search indexing pure and memoized.

### Release verification

- Settings schema migration tests.
- Backend route and repository tests.
- Frontend reducer and search tests.
- Component tests for each category.
- End-to-end reload/save/discard/conflict tests.
- Degraded/offline provider and worker tests.
- Existing RPG architecture-compliance and deterministic gates.
- Manual visual comparison against the approved mockup.

Launch acceptance:

- No regression in module-specific workflows.
- No sensitive configuration appears in the browser payload or diagnostics.
- Saved values survive restart and reload.
- New-session/new-job applicability is explained correctly.
- All supported central defaults are consumed by their owning modules.

---

## Recommended PR sequence

1. SCC-0.1 registry types and tests.
2. SCC-0.2 ownership map.
3. SCC-0.3 defaults/merge/migration helpers.
4. SCC-1.1 OpenAPI schemas.
5. SCC-1.2 repository persistence.
6. SCC-1.3 compatibility route.
7. SCC-1.4 validation/redaction.
8. SCC-2.1 typed client.
9. SCC-2.2 draft reducer/store.
10. SCC-2.3 local preference adapter.
11. SCC-3.1 route composition cleanup.
12. SCC-3.2 shell and responsive frame.
13. SCC-3.3 form primitives.
14. SCC-4.1 default-provider card.
15. SCC-4.2 provider summaries.
16. SCC-4.3 configure/test flow.
17. SCC-4.4 routing/fallback.
18. SCC-5.1 status rail.
19. SCC-5.2 search.
20. SCC-5.3 save/discard/conflict UX.
21. SCC-6 Appearance & Accessibility.
22. SCC-7 Assistant & Chat.
23. SCC-8 Voice & Audio.
24. SCC-9 Storyteller & Podcast.
25. SCC-10.1 RPG campaign defaults.
26. SCC-10.2 RPG systems.
27. SCC-10.3 RPG routing.
28. SCC-10.4 Hermes RPG defaults.
29. SCC-11 Images & Speech Input.
30. SCC-12.1 tool summary.
31. SCC-12.2 tool detail.
32. SCC-12.3 Hermes integration page.
33. SCC-13 operational categories.
34. SCC-14.1 duplicate-reader cleanup.
35. SCC-14.2 legacy frontend removal.
36. SCC-14.3 API compatibility removal.
37. SCC-15 production launch gate.

## Source files expected to change

Primary frontend entry points:

- `src/apps/web/src/features/platform/SettingsWorkspace.tsx`
- `src/apps/web/src/features/platform/PlatformModuleWorkspace.tsx`
- `src/apps/web/src/features/platform/HermesStatusCard.tsx`
- `src/apps/web/src/api/client.ts`
- `src/apps/web/src/api/generated/types.ts`

New frontend area:

- `src/apps/web/src/features/settings/`

Module adoption points:

- `src/apps/web/src/features/assistant-workspace/preferences.ts`
- `src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx`
- `src/apps/web/src/features/chatbot/AssistantToolSettingsPanel.tsx`
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

Backend work should remain in the existing owner of `/api/settings`, its OpenAPI schemas, and the project's established persistence/service layer rather than introducing a second settings service.

## Definition of done

The Settings Control Center is complete when:

- the approved visual shell is implemented
- supported global and module defaults are typed and persisted
- each migrated workspace consumes the same effective settings
- per-session and per-job overrides still work
- status and environment information remain clearly read-only
- search, dirty state, save, discard, validation, and conflict recovery work
- compatibility paths have an explicit removal point
- accessibility, responsive, security, migration, and deterministic regression gates pass
