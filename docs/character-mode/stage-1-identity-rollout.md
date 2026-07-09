# Character Mode Stage 1 — identity without memory

Status: ready for a deployment-specific rehearsal.

Stage 1 validates the merged Character Mode identity, profile, context-segment, live-call runtime, provider-streaming, and TTS paths while every character-memory capability remains disabled.

The preflight is deliberately two-part. `prepare` exercises the running deployment and writes a restart checkpoint. After restarting Omnix, `verify-restart` confirms that the profile version, active segment, effective identity hash, renderer voice, and memory-off state persisted. A final `pass` is impossible without the restart verification.

## Required flags

Start Omnix with only Character Mode enabled:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Do not enable character memory, shared System Assistant memory, or Character Hermes during Stage 1. Existing normal Chat-memory settings may remain at their current values because the Stage 1 character sessions explicitly use `read_memory=false` and `write_memory=false`.

Windows `cmd.exe` example for a temporary rehearsal shell:

```bat
set OMNIX_CHARACTER_MODE_ENABLED=1
set OMNIX_CHARACTER_MEMORY_ENABLED=0
set OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
set OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
start_all.bat
```

## What the harness checks

The HTTP preflight verifies all of the following against the running gateway:

1. Gateway health.
2. The requested character profile exists, is active, and has a stable version.
3. Selecting a renderer voice without a character remains **System Assistant** mode.
4. A Character session resolves the requested server-owned character, profile version, effective identity hash, greeting, and speech style.
5. Character memory read, write, shared-memory access, snapshots, and selected-record counts remain off.
6. System Assistant → Character → System Assistant/Character transitions create distinct persisted context segments.
7. Text streaming produces a first token and records latency without storing response text in the report.
8. Streaming TTS produces a first audio chunk using the resolved Character runtime and records latency without storing audio.
9. Character-owned memory records and pending suggestions are unchanged after the turn settles.
10. A second run after service restart confirms persistence of the profile version, segment, identity hash, renderer voice, and memory-off state.

Generated reports contain IDs, hashes, counts, status codes, and timings only. They do not contain personality prompts, user text, assistant text, memory contents, or audio.

## Prepare rehearsal

From the repository root:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --base-url http://127.0.0.1:5050 ^
  --character-id stage1-maya ^
  --display-name "Maya Stage 1" ^
  --provider-id lmstudio ^
  --model-id YOUR_LOADED_MODEL_ID
```

Default outputs are ignored runtime artifacts:

```text
resources/data/test-results/character-mode-stage1-checkpoint.json
resources/data/test-results/character-mode-stage1-prepare-report.json
```

A successful preparation normally returns:

```text
decision = needs_review
```

That is expected because restart persistence has not yet been verified. A `blocked` decision means one or more required checks failed and the rollout must not continue.

### Existing test character

The harness is idempotent when the existing profile exactly matches the requested profile. It fails rather than silently changing an existing profile. To intentionally create a new profile version that matches the requested Stage 1 settings, add:

```text
--update-existing-character
```

Use a dedicated rehearsal character ID instead of modifying a production character whenever possible.

## Optional governed cloned voice

Omit `--voice-asset-id` to rehearse identity and live TTS with the deployment's default renderer.

To use an already governed cloned voice:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --base-url http://127.0.0.1:5050 ^
  --character-id stage1-maya ^
  --voice-asset-id voice-cloning:maya ^
  --provider-id lmstudio ^
  --model-id YOUR_LOADED_MODEL_ID
```

The voice must already have:

- a voice subject/owner;
- source type and source reference;
- creator ID;
- granted consent;
- a source SHA-256;
- `character` and `live_call` allowed uses;
- `deletion_state=active`.

The harness never grants consent implicitly. To explicitly record governance during the rehearsal, all of these arguments are required:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --base-url http://127.0.0.1:5050 ^
  --character-id stage1-maya ^
  --voice-asset-id voice-cloning:maya ^
  --apply-voice-governance ^
  --confirm-voice-consent ^
  --voice-subject-owner "VOICE SUBJECT OR OWNER" ^
  --voice-source-type user_recording ^
  --voice-source-reference "CONSENT OR SOURCE REFERENCE" ^
  --voice-creator-id user:local ^
  --provider-id lmstudio ^
  --model-id YOUR_LOADED_MODEL_ID
```

`--confirm-voice-consent` is an operational assertion by the person running the command. Do not use it without actual authority and evidence from the voice subject/owner.

## Provider or TTS diagnostics

The full Stage 1 decision requires live provider streaming and live streaming TTS. For contract-only diagnosis, either path can be skipped:

```text
--skip-generation
--skip-tts
```

Skipped paths are marked `review`, so the report remains `needs_review` even after restart verification. These switches are for narrowing failures, not for approving Stage 1.

The preflight measures:

- server-reported live-call runtime preload time;
- request-to-first streamed text chunk;
- request-to-first streamed audio chunk;
- first audio chunk byte estimate;
- assistant response character count, without retaining the response itself.

## Restart verification

After `prepare` completes without a `blocked` decision:

1. Stop all Omnix services cleanly.
2. Start them again with the same Stage 1 flags and storage paths.
3. Run:

```bat
python scripts\character_mode_stage1_preflight.py verify-restart ^
  --base-url http://127.0.0.1:5050
```

Default final report:

```text
resources/data/test-results/character-mode-stage1-final-report.json
```

A final `pass` means every automated Stage 1 check, including persistence across restart, passed. `needs_review` means a live path was intentionally skipped. `blocked` means rollout must stop.

## Browser confirmation

After the automated final report passes, perform one short browser check against the same deployment:

- Open the Chat workspace and select the rehearsal session.
- Confirm the visible badge says the expected character name.
- Start a live call and confirm the greeting is spoken once.
- Confirm the selected voice sounds correct but changing only the voice does not change the character badge.
- Switch to System Assistant and confirm the badge changes immediately.
- Switch back to the character with topic carryover disabled and confirm the prior identity style is not replayed as current context.
- Open Memory management and confirm the rehearsal session still shows memory read off, memory write off, and no active snapshot.

Record only pass/fail observations in `stage-1-rehearsal-results.md`; do not paste transcripts or consent evidence into repository documentation.

## Rollback

If any Stage 1 check fails, disable Character Mode and restart:

```text
OMNIX_CHARACTER_MODE_ENABLED=0
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Feature rollback does not delete the rehearsal profile, version history, session, cloned voice, or voice-governance metadata. Any cleanup must be a separate explicit action.

## Stage 1 exit criteria

Stage 1 may advance to the read-only memory pilot only when:

- the final automated report is `pass`;
- the browser confirmation is complete;
- no character-memory records, candidates, snapshots, or shared-memory access appeared;
- System Assistant behavior remains normal with Character Mode disabled;
- any cloned voice used in the rehearsal has valid governance and live-call permission;
- latency is acceptable for the deployment or has an explicitly accepted follow-up issue.
