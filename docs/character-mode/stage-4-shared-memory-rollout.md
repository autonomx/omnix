# Character Mode Stage 4 - read-only shared System Assistant memory

Status: local deployment rehearsal passed on 2026-07-09.

Stage 4 lets a character read explicitly allowlisted, normal-sensitivity System Assistant memory as background context. The character's own memory controls remain independent, and shared records cannot be created, edited, approved, or forgotten through a character session.

## Required flags

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=1
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

The character profile must own a policy such as:

```json
{"access":"read_only","allowed_categories":["fact","preference"]}
```

The participating session uses `shared_memory_access=read_only`. Keep non-participating sessions at `none`.

## Prepare

With LM Studio serving the selected model and Omnix running with the flags above:

```bat
python scripts\character_mode_stage4_preflight.py prepare ^
  --model-id "gemma-4-e4b-uncensored-hauhaucs-aggressive"
```

Expected result:

```text
decision = needs_review
```

The harness creates content-marked synthetic System Assistant records covering an allowed fact, a non-allowlisted category, sensitive content, and session-only content. It verifies streamed selection diagnostics, shared-off isolation, `403` write enforcement, and clean context segments when the bridge is disabled and re-enabled.

Stop if prepare returns `blocked`. Do not run restart verification or advance to Stage 5.

## Restart verification

Restart all Omnix services with exactly the same flags and storage paths, confirm LM Studio still serves the model, then run:

```bat
python scripts\character_mode_stage4_preflight.py verify-restart
```

Expected result:

```text
decision = pass
```

The passing final run verifies the persisted policy, identity hash, segment, and selected record IDs, then deletes all four synthetic records and all three temporary sessions.

Default ignored artifacts:

```text
resources/data/test-results/character-mode-stage4-checkpoint.json
resources/data/test-results/character-mode-stage4-prepare-report.json
resources/data/test-results/character-mode-stage4-final-report.json
```

## Rollback

Set participating sessions to `shared_memory_access=none`, set `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0`, and restart Omnix. Native character memory and System Assistant memory remain stored under their original owners.

## Exit criteria

Advance to Stage 5 only when the final report is `pass`, only allowlisted normal non-session System Assistant records are selected, character write operations return `403`, off/on switching creates clean segments, restart persistence passes, and fixture cleanup passes.
