# Character Mode Stage 5 - governed cloned voice and live call

Status: local deployment rehearsal passed on 2026-07-09.

Stage 5 links one explicitly consented cloned voice to a controlled character and validates the server-owned live-call runtime. Never mark a legacy voice as granted without confirmation from the owner or authorized operator.

## Governance prerequisite

The selected voice must have all of the following persisted through the voice governance API:

- subject or owner;
- source type and source reference;
- creator ID;
- `consent_status=granted`;
- allowed uses containing `character` and `live_call`;
- source SHA-256;
- `deletion_state=active`.

Other cloned voices remain independently governed and unverified unless explicitly approved.

## Prepare

This deployment reuses the Stage 1 identity/audio harness because it already validates the Stage 5 live path. Use isolated Stage 5 artifact paths:

```bat
python scripts\character_mode_stage1_preflight.py prepare ^
  --character-id stage5-maya ^
  --display-name "Maya Stage 5" ^
  --voice-asset-id "voice-cloning:Maya" ^
  --provider-id lmstudio ^
  --model-id "gemma-4-e4b-uncensored-hauhaucs-aggressive" ^
  --update-existing-character ^
  --checkpoint resources/data/test-results/character-mode-stage5-checkpoint.json ^
  --report resources/data/test-results/character-mode-stage5-prepare-report.json
```

Expected result: `decision = needs_review`.

The prepare run verifies governance, renderer-only System Assistant isolation, server-resolved character identity, live-call profile/voice/greeting resolution, bounded speech controls, clean identity segments, streamed generation, streamed cloned-voice PCM, and zero memory activity for the controlled call.

## Restart verification

Restart all Omnix services with the same Character flags, model paths, and provider configuration. Wait for `/api/tts/runtime/status` to report `ready`, then run:

```bat
python scripts\character_mode_stage1_preflight.py verify-restart ^
  --checkpoint resources/data/test-results/character-mode-stage5-checkpoint.json ^
  --report resources/data/test-results/character-mode-stage5-final-report.json
```

Expected result: `decision = pass`.

The Stage 5 report retains the Stage 1 report format because it deliberately reuses the proven identity/audio harness. Artifact names and character IDs keep the deployment evidence isolated.

## Rollback

Unlink the voice from the character, set consent to `revoked`, remove `character` or `live_call` from allowed uses, or set a non-active deletion state. Restart Omnix after launcher model-path changes. Voice rollback does not delete the character, memory, or transcripts.
