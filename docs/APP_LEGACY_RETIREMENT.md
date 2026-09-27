# Application legacy cleanup

The React app in `src/apps/web` and `app.gateway.main:app` are the supported
browser stack. `src/main.py`, `src/launch.py`, and application factory callers
now use that gateway.

## Removed implementations

| Apps | Retired implementation | Current owner |
| --- | --- | --- |
| Chat | `run_app.py` chat stream, greetings, conversation websocket | `app.chat` and gateway chat/live speech routes |
| Storyteller and podcast | `run_app.py` generation, parsing, episode and voice-profile routes | Shared feature jobs, assets, and React workspaces |
| Voice and voice cloning | `run_app.py` voice studio, cloning, TTS endpoints and websocket | `app.jobs.voice_inline`, gateway voice/TTS routes and speech workers |
| STT | `run_app.py` transcription routes and unused `parakeet_stt_legacy_server.py` | Gateway speech jobs, live speech and `parakeet_stt_runtime` |
| Image generation | `run_app.py` image-router assembly and filename-based media serving | Gateway image workspace, shared assets and image worker |
| RPG | `run_app.py` and package-level duplicate router assembly | Gateway RPG world, session, map and inspection routes |
| Background speech jobs | Unused `app/job_queue.py` and its submission adapter | Shared job execution and voice feature jobs |

Tests requiring the removed servers and queues were retired. Shared audio
utility tests remain. Retirement coverage checks the gateway entrypoints and
the absence of obsolete application routes.

## Retained dependencies

- Trading uses its current gateway and registered strategies/monitors. Older
  numbered research strategies remain registered; a version suffix does not
  establish that they are unused.
- `openai_api.py` is a separately documented client integration with launch
  scripts. It is not a previous browser app.
- TTS, Parakeet, image and runtime-control worker servers are active services.
- Persistence migrations, legacy session/document imports, RPG saved-state
  adapters and memory migration code preserve existing user data.
- `RpgCreateCampaignWizardLegacy.tsx` is rendered by the current campaign wizard.
  `legacy-layout.css` supplies the current shell layout.

No saved books, campaigns, voices, model files or generated media are removed.
