# Character Mode Stage 1 — identity without memory

Status: ready for a deployment-specific rehearsal.

Stage 1 validates the merged Character Mode identity, profile, context-segment, live-call runtime, provider-streaming, and TTS paths while every character-memory capability remains disabled.

The preflight is deliberately two-part. `prepare` exercises the running deployment and writes a restart checkpoint. After restarting Omnix, `verify-restart` confirms that the profile version, active segment, effective identity hash, renderer voice, and memory-off state persisted. A final `pass` is impossible without restart verification.

## Launcher topology

`start_all.bat` starts the launcher dashboard on `127.0.0.1:5055`, but the active Omnix gateway used by the React app and this rehearsal is:

```text
http://127.0.0.1:8000
```

The preflight defaults to that gateway. Port `5050` is not part of the current `start_all.bat` runtime topology.

Streaming TTS is measured through the active gateway's raw PCM websocket:

```text
ws://127.0.0.1:8000/api/tts/stream/websocket
```

The retired `/api/tts/stream/server-sent-events` path is not used by the Stage 1 harness.

## Required flags

Start Omnix with only Character Mode enabled:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Existing normal Chat-memory settings may remain unchanged because the Stage 1 character sessions explicitly use `read_memory=false` and `write_memory=false`.

Windows `cmd.exe` example:

```bat
set OMNIX_CHARACTER_MODE_ENABLED=1
set OMNIX_CHARACTER_MEMORY_ENABLED=0
set OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
set OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
start_all.bat
```

## Provider prerequisites

Before running `prepare`, start LM Studio's local server and load the exact model selected for the rehearsal. The configured Omnix LM Studio endpoint is normally:

```text
http://127.0.0.1:1234/v1
```

Confirm that LM Studio's Developer/API server reports a loaded model. A connection failure at `/v1/chat/completions` is an operational blocker; do not run restart verification until the provider check succeeds.

The launcher must also show the Omnix TTS service as running. The preflight uses the gateway websocket rather than connecting directly to port `5101`, so it verifies the same transport surface used by the current gateway runtime.

## What the harness checks

The HTTP/websocket preflight verifies:

1. Gateway health.
2. The requested character profile exists, is active, and has a stable version.
3. Selecting a renderer voice without a character remains **System Assistant** mode.
4. A Character session resolves the requested server-owned character, profile version, effective identity hash, greeting, and speech style.
5. Character memory read, write, shared-memory access, snapshots, and selected-record counts remain off.
6. System Assistant → Character → System Assistant/Character transitions create distinct persisted context segments.
7. Text streaming produces a first token and records latency without storing response text in the report.
8. The gateway PCM websocket produces a first audio frame and records latency without storing audio.
9. Character-owned memory records and pending suggestions are unchanged after the turn settles.
10. A second run after service restart confirms persistence of the profile version, segment, identity hash, renderer voice, and memory-off state.

Generated reports contain IDs, hashes, counts, status codes, and timings only. They do not contain personality prompts, user text, assistant text, memory contents, or audio.

## Prepare rehearsal

From the repository root:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --base-url http://127.0.0.1:8000 ^
  --character-id stage1-maya ^
  --display-name "Maya Stage 1" ^
  --provider-id lmstudio ^
  --model-id "YOUR_EXACT_LOADED_MODEL_ID"
```

The `--base-url` argument is optional because `http://127.0.0.1:8000` is now the default.

Default ignored runtime outputs:

```text
resources/data/test-results/character-mode-stage1-checkpoint.json
resources/data/test-results/character-mode-stage1-prepare-report.json
```

A healthy preparation returns:

```text
decision = needs_review
```

That is expected because restart persistence remains unverified. A `blocked` decision means rollout must stop. Correct the blocker and rerun `prepare`; do not reuse a checkpoint from a blocked run.

### Existing rehearsal character

The harness is idempotent when the existing profile exactly matches the requested profile. It fails rather than silently changing an existing profile. To intentionally create a matching new profile version, add:

```text
--update-existing-character
```

Use a dedicated rehearsal character ID instead of modifying a production character.

## Optional governed cloned voice

Omit `--voice-asset-id` to use the deployment's default renderer.

A linked cloned voice must already have a subject/owner, source type and reference, creator ID, granted consent, source SHA-256, `character` and `live_call` allowed uses, and `deletion_state=active`.

The harness never grants consent implicitly. Explicit governance updates require all of:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --character-id stage1-maya ^
  --voice-asset-id voice-cloning:maya ^
  --apply-voice-governance ^
  --confirm-voice-consent ^
  --voice-subject-owner "VOICE SUBJECT OR OWNER" ^
  --voice-source-type user_recording ^
  --voice-source-reference "CONSENT OR SOURCE REFERENCE" ^
  --voice-creator-id user:local ^
  --provider-id lmstudio ^
  --model-id "YOUR_EXACT_LOADED_MODEL_ID"
```

`--confirm-voice-consent` is an operational assertion. Do not use it without actual authority and evidence from the voice subject or owner.

## Diagnostic-only skips

The full decision requires both live provider streaming and live gateway TTS. For diagnosis only:

```text
--skip-generation
--skip-tts
```

Skipped paths remain `review`; they cannot approve Stage 1.

## Restart verification

After `prepare` completes without `blocked`:

1. Stop all Omnix services cleanly.
2. Start them again with the same Stage 1 flags and storage paths.
3. Run:

```bat
python scripts\character_mode_stage1_preflight.py verify-restart ^
  --base-url http://127.0.0.1:8000
```

Default final report:

```text
resources/data/test-results/character-mode-stage1-final-report.json
```

A final `pass` means every automated Stage 1 check, including persistence across restart, passed. `needs_review` means a live path was intentionally skipped. `blocked` means rollout must stop.

## Browser confirmation

After the automated final report passes:

- Confirm the visible badge shows the rehearsal character.
- Start a live call and confirm the greeting is spoken once.
- Confirm changing only the renderer voice does not change the character badge.
- Switch to System Assistant and confirm the badge changes immediately.
- Switch back with topic carryover disabled and confirm the previous identity style is not replayed as current context.
- Confirm Memory management still reports read off, write off, and no active snapshot.

Record content-free pass/fail observations in `stage-1-rehearsal-results.md`.

## Rollback

On any Stage 1 failure, disable Character Mode and restart:

```text
OMNIX_CHARACTER_MODE_ENABLED=0
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Rollback does not delete the rehearsal profile, version history, session, cloned voice, or governance metadata.

## Exit criteria

Advance to the read-only memory pilot only when:

- the final automated report is `pass`;
- the browser confirmation is complete;
- no character-memory records, candidates, snapshots, or shared-memory access appeared;
- System Assistant works normally after Character Mode rollback;
- any cloned voice has valid governance and live-call permission;
- latency is acceptable or has an explicitly accepted follow-up issue.
