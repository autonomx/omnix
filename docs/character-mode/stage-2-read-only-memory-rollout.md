# Character Mode Stage 2 — read-only character memory pilot

Status: operator preflight ready; deployment rehearsal pending.

Stage 2 enables the native Omnix character-memory reader for one controlled pilot while keeping conversational writes, shared System Assistant memory, and Character Hermes disabled.

The preflight is two-part. `prepare` creates controlled synthetic owner fixtures, proves prompt selection and write rejection, and writes a restart checkpoint. `verify-restart` confirms persistence, repeats the read-only checks, validates forget propagation, and removes the synthetic records and temporary setup sessions.

## Required flags

Start Omnix with:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

The pilot sessions are fixed to:

```text
read_memory=true
write_memory=false
shared_memory_access=none
transcript_policy=persistent
```

Normal suggestion processing may remain at its deployment setting. The pilot deliberately sends a message that could produce a memory candidate; the read-only owner policy must prevent that candidate from being created.

## Controlled setup boundary

The preflight creates short-lived setup sessions for three owners:

- `character/stage2-maya`;
- `character/stage2-alex`;
- `system/system-assistant`.

The two character setup sessions temporarily use `write_memory=true` only to create one pinned synthetic record per owner through the normal management API. They do not call the model and are not pilot conversations. The real Maya and Alex pilot sessions remain read-only throughout.

After successful restart verification, the preflight:

1. forgets the Maya synthetic record;
2. confirms Maya snapshot projection no longer exposes the forgotten record without affecting Alex or System Assistant records;
3. refreshes Maya's snapshot and confirms the forgotten record is absent;
4. deletes the Alex and System Assistant synthetic records;
5. disables the setup-session character write policies;
6. deletes all temporary setup sessions and the Alex isolation-control session.

The canonical repository forget behavior purges matching `memory_snapshot_items` rows immediately. A missing snapshot item is therefore successful propagation, not a cleanup failure. A retained but inactive item is also accepted for compatible repository implementations, provided its content is not active.

The Maya pilot session remains as content-free deployment evidence.

## What the preflight verifies

1. Gateway health and the configured LM Studio model.
2. Active Maya and Alex synthetic character profiles.
3. Owner-specific pinned records for Maya, Alex, and System Assistant.
4. Maya and Alex pilot sessions use `read_memory=true`, `write_memory=false`, and `shared_memory_access=none`.
5. Memory listing and snapshot selection include the active character's record and exclude the other character and System Assistant records.
6. Provider completion metadata reports `owner_type=character`, the expected owner ID, and the expected selected memory ID.
7. A candidate-shaped user message does not produce a pending suggestion.
8. An explicit `remember that ...` command returns `mutated=false`.
9. A direct management API write through the read-only pilot returns HTTP `403` with `character_memory_write_disabled`.
10. Turning memory off creates a new segment and removes the active snapshot and provider memory context.
11. Turning read-only memory back on creates another clean segment and a fresh owner-bound snapshot.
12. Profile identity, segment, policy, snapshot, and selected owner memory survive restart.
13. Forget propagation and refreshed snapshots remain owner-isolated.

Reports contain only IDs, hashes, counts, policies, and timings. Synthetic memory text and model output are not written to reports.

## Prepare

Pull current `main`, start LM Studio's API server, and load the same model used for Stage 1 or another explicitly selected model.

Start Omnix from `cmd.exe`:

```bat
set OMNIX_CHARACTER_MODE_ENABLED=1
set OMNIX_CHARACTER_MEMORY_ENABLED=1
set OMNIX_CHAT_MEMORY_ENABLED=1
set OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
set OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
start_all.bat
```

Run from the repository root:

```bat
python scripts\character_mode_stage2_preflight.py prepare ^
  --model-id "gemma-4-e4b-uncensored-hauhaucs-aggressive"
```

The gateway defaults to:

```text
http://127.0.0.1:8000
```

Optional arguments include:

```text
--provider-id lmstudio
--maya-character-id stage2-maya
--alex-character-id stage2-alex
--run-id stage2-readonly-v1
--settle-seconds 4
--token-budget 4000
```

Default ignored outputs:

```text
resources/data/test-results/character-mode-stage2-checkpoint.json
resources/data/test-results/character-mode-stage2-prepare-report.json
```

Expected prepare decision:

```text
decision = needs_review
```

That is expected only because restart persistence remains pending. Any `blocked` result stops the rollout. Do not run restart verification with a blocked prepare result.

## Restart verification and cleanup

After a non-blocked prepare run:

1. Stop all Omnix services cleanly.
2. Restart with exactly the same Stage 2 flags and storage paths.
3. Confirm LM Studio still serves the same loaded model.
4. Run:

```bat
python scripts\character_mode_stage2_preflight.py verify-restart
```

Default final report:

```text
resources/data/test-results/character-mode-stage2-final-report.json
```

Expected final decision:

```text
decision = pass
```

A successful final run also cleans up the synthetic memory records and temporary setup/control sessions. If cleanup fails, the result is `blocked`; do not proceed to Stage 3 until the owner-isolation cleanup check passes.

## Recovery from the known snapshot-purge assertion

An early Stage 2 harness incorrectly required the forgotten Maya record to remain represented as an inactive snapshot item. The repository actually purges the snapshot item, so the server had already completed the forget operation before the harness blocked.

Use recovery only when the failed final report shows all three restart checks passing and this exact cleanup failure:

```text
cleanup.forget_isolation: forget did not invalidate the active Maya snapshot item
```

Pull the patched `main`, keep Omnix running with the same Stage 2 flags, and run:

```bat
python scripts\character_mode_stage2_preflight.py resume-cleanup
```

The command validates the failed report against the checkpoint, confirms the Maya record is absent from both the owner listing and active snapshot, verifies Alex and System Assistant records were preserved, refreshes Maya's snapshot, deletes the remaining synthetic records, disables temporary write policies, and removes the temporary setup/control sessions.

Default recovery report:

```text
resources/data/test-results/character-mode-stage2-recovery-report.json
```

Expected recovery decision:

```text
decision = pass
```

Do not use `resume-cleanup` for a different failed check. It rejects unrelated failures and performs no cleanup.

## Browser confirmation

After the final automated or recovery report passes:

- Open the retained Maya Stage 2 pilot session.
- Confirm the Character badge shows Maya Stage 2.
- Confirm Memory management reports read on, write off, and shared memory none.
- Confirm the snapshot is present but the cleaned-up synthetic record is no longer active.
- Send an ordinary message and confirm the UI does not show a new pending suggestion for that read-only session.
- Attempt an explicit remember command and confirm the UI reports that character-memory writing is disabled.
- Switch memory off and back to read-only and confirm the visible identity remains Maya while context segments change.
- Confirm a System Assistant session does not display Maya or Alex relationship memory.

Record content-free pass/fail observations in `stage-2-rehearsal-results.md`.

## Rollback

To return to the passed Stage 1 posture:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Restart Omnix after changing the flags. Disabling character memory does not delete approved owner records, but the Stage 2 harness removes its own synthetic records after a successful run.

For a full Character Mode rollback, also set `OMNIX_CHARACTER_MODE_ENABLED=0`.

## Exit criteria

Advance to Stage 3 explicit character-memory writes only when:

- the Stage 2 final or recovery report is `pass`;
- browser confirmation is complete;
- prompt metadata selected only the active character owner;
- no pending suggestions or approved records were created by the read-only pilot;
- explicit command and management writes were rejected;
- memory-off and read-only transitions created clean segments and snapshots;
- forget propagation preserved other owners;
- synthetic fixtures were cleaned up successfully.
