# PostgreSQL Post-Cutover Wiring Audit

**Audit branch:** `agent/postgresql-settings-wiring-audit`  
**Baseline:** `main` at `19f815c6d81807c49ba812256c8b7dfcdb290667`  
**Scope:** application settings, provider selection, runtime caches, module-default adoption, PostgreSQL bootstrap, and remaining compatibility surfaces after centralized PostgreSQL authority.

## Executive summary

The default LLM provider control was not reaching PostgreSQL successfully. The Settings Control Center submitted both the typed profile patch and legacy compatibility fields. The compatibility saver always attempted to persist provider secrets, while the PostgreSQL runtime deliberately replaces that writer with a fail-closed `LegacyPersistenceRetired` adapter. A provider-only change therefore failed before the application settings document was committed.

The same path also performed two application-settings writes: one through the legacy saver and a second after applying the typed profile. That was non-atomic and unnecessary because the typed profile synchronizer already projects provider and provider-config changes into the legacy runtime keys consumed by `app.shared.get_provider()`.

This branch fixes that critical path by applying compatibility and typed-profile mutations to one in-memory settings document, writing secrets only when a real key changed, and committing application settings once after validation.

## Audit matrix

| Area | Status before audit | Finding | Action |
|---|---|---|---|
| Settings Control Center provider save | **Broken** | Ordinary provider changes invoked the retired plaintext secret writer under PostgreSQL and returned a failed save. | Fixed on this branch. |
| Settings write atomicity | **Broken** | Combined SCC requests wrote legacy settings and typed settings separately. | Fixed: one validated authoritative settings commit. |
| Provider secret editing | **Misleading** | PostgreSQL runtime reads OpenRouter/Cerebras keys from environment variables and intentionally rejects plaintext writes, while the UI still rendered editable password fields. | Fixed: fields are read-only environment status and settings requests omit secret bytes. |
| LLM provider cache | **Wired** | Cache key includes provider, base URL, model, and API-key fingerprint; settings/secret changes invalidate it. | Retain existing behavior and add the PostgreSQL save regression test. |
| TTS provider cache | **Stale-config risk** | Cache identity is provider name only. Changing Qwen model directory, device, dtype, or generation settings while keeping the same provider reuses the old instance. | Follow-up: fingerprint effective TTS configuration or explicitly invalidate the audio cache. |
| STT provider cache | **Stale-config risk** | Cache identity is provider name only. Changing the Parakeet base URL while keeping `parakeet` selected reuses the old instance. | Follow-up: fingerprint effective STT configuration or explicitly invalidate the audio cache. |
| Chatbot global provider/model defaults | **Partially wired** | Backend generation falls back to `app.shared.get_provider()` when a session/request has no override, so new override-free sessions use the PostgreSQL default. The web form still initializes from Vite environment values instead of the settings profile, and existing sessions correctly retain their session override. | Follow-up: use the central profile for new-chat form defaults while preserving existing-session overrides. |
| Assistant defaults | **Not centralized at runtime** | Chatbot personality/voice defaults still load from browser storage, despite the ownership map targeting the settings API. | Follow-up module-adoption slice. |
| Storyteller defaults | **Not wired** | Provider, tone, and writing-style defaults are hard-coded/local component state and do not load the central `storyteller` namespace. | Follow-up module-adoption slice. |
| Podcast defaults | **Not wired** | Format, duration, tone, language, generation style, autoplay, playback, output settings, and effects are hard-coded/local component state. | Follow-up module-adoption slice. |
| Image Generation defaults | **Not wired** | The workspace does not load the central `image` namespace. | Follow-up module-adoption slice. |
| Voice / Voice Cloning / STT defaults | **Partially wired** | These workspaces load the settings profile, but each still needs field-by-field acceptance coverage to distinguish central defaults from job overrides. | Add adoption contract tests. |
| RPG campaign defaults | **Partially wired** | The campaign wizard loads the settings profile. Existing campaigns remain session-owned by design. | Retain boundary; add regression coverage for new campaigns only. |
| Global model/routing defaults | **Mostly cosmetic** | `global.models` and `global.routing` are editable/persisted but have no general runtime resolver consumed by all modules. | Introduce a shared effective-default resolver before declaring these controls production-wired. |
| PostgreSQL gateway bootstrap | **Wired** | The supported gateway launcher establishes PostgreSQL authority before importing/serving the gateway. | Retain exact-startup guard coverage. |
| Legacy JSON/SQLite runtime authority | **Retired** | Runtime adapters fail closed and replace active stores. | Retain retirement guards; do not restore file authority. |

## Critical root cause

The failing sequence was:

1. The frontend changed `global.providers.llm` and generated a request containing both `settings_profile_patch` and the compatibility `provider` field.
2. `settings_control.save_settings_payload()` called the legacy settings saver first.
3. The legacy saver called `save_secrets()` unconditionally, even though no key changed.
4. PostgreSQL startup had installed `reject_plaintext_provider_secret_write()` as the secret save callback.
5. The request failed before `save_settings()` could commit the selected provider.

The corrected sequence is:

1. Load application settings and environment-owned secret state once.
2. Apply compatibility fields in memory.
3. Apply and validate the typed settings-profile patch in memory.
4. Persist secrets only when a real unmasked key changed; PostgreSQL rejects that unsupported operation before any application-settings commit.
5. Commit the authoritative application settings document once.
6. Let `save_settings()` invalidate the LLM provider cache when effective provider inputs changed.

## Verification added

The SCC adapter regression suite now covers:

- a PostgreSQL provider change succeeding without invoking the retired secret writer;
- exactly one authoritative application-settings write for a combined compatibility/profile request;
- the selected provider being synchronized into both the runtime legacy key and typed profile;
- a real provider-key edit failing closed before any settings commit;
- continued legacy-file behavior for installations/tests that explicitly use the legacy persistence boundary;
- frontend save requests never serializing OpenRouter or Cerebras API-key bytes.

## Remaining implementation order

1. Make TTS/STT cache identity configuration-sensitive.
2. Add one shared frontend `effectiveSettingsDefaults` adapter and wire Chatbot, Storyteller, Podcast, and Image Generation.
3. Add field-level adoption tests for Voice, Voice Cloning, STT, and RPG new-campaign creation.
4. Add a source guard that prevents a setting marked `targetOwner: settings-api` from remaining permanently unconsumed by its module.
