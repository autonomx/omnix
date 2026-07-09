# Character Mode Stage 3 - explicit character-memory writes

Status: operator preflight ready; deployment rehearsal pending.

Stage 3 enables explicit writes for one controlled character-memory pilot while keeping shared System Assistant memory and Character Hermes disabled. Inferred memory remains review-gated: it may create pending candidates, but pending candidates must not enter prompts until approved and the active snapshot is refreshed.

## Required flags

Start Omnix with:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

The selected pilot session uses:

```text
read_memory=true
write_memory=true
shared_memory_access=none
transcript_policy=persistent
```

The write-only control uses:

```text
read_memory=false
write_memory=true
shared_memory_access=none
```

## What the preflight verifies

1. Gateway health and active synthetic Stage 3 characters.
2. A read/write Maya pilot can save explicit memory to `character/stage3-maya`.
3. A write-only Maya control can save memory while exposing no readable memory context.
4. Inferred content creates exactly one pending character-owned candidate.
5. Pending candidates are not approved records and do not appear in the active snapshot.
6. Approval creates an approved record, but it becomes prompt-eligible only after snapshot refresh.
7. Rejected candidates leave the pending queue and remain excluded.
8. Alex owner listing and snapshot exclude Maya records.
9. Restart preserves write policy, identity, approved records, and refreshed snapshot.
10. Final verification removes synthetic records, resolved candidate rows, and temporary sessions.

Reports contain only IDs, hashes, counts, policies, and timings. Synthetic memory text, user prompts, model output, and transcripts are not written to reports.

## Prepare

Run from the repository root after Stage 2 evidence has merged:

```bat
python scripts\character_mode_stage3_preflight.py prepare ^
  --model-id "gemma-4-e4b-uncensored-hauhaucs-aggressive"
```

Optional arguments include:

```text
--base-url http://127.0.0.1:8000
--provider-id lmstudio
--maya-character-id stage3-maya
--alex-character-id stage3-alex
--run-id stage3-write-v1
--settle-seconds 8
--token-budget 4000
```

Default ignored outputs:

```text
resources/data/test-results/character-mode-stage3-checkpoint.json
resources/data/test-results/character-mode-stage3-prepare-report.json
```

Expected prepare decision:

```text
decision = needs_review
```

That is expected only because restart persistence remains pending. Any `blocked` result stops the rollout. If the pending suggestion does not appear before `--settle-seconds`, confirm the suggestion worker is running and do not proceed to restart verification.

## Restart verification and cleanup

After a non-blocked prepare run:

1. Stop all Omnix services cleanly.
2. Restart with exactly the same Stage 3 flags and storage paths.
3. Confirm LM Studio still serves the selected model.
4. Run:

```bat
python scripts\character_mode_stage3_preflight.py verify-restart
```

Default final report:

```text
resources/data/test-results/character-mode-stage3-final-report.json
```

Expected final decision:

```text
decision = pass
```

A successful final run removes the approved synthetic Stage 3 records, resolved suggestion candidate rows, and temporary sessions. If cleanup fails, the result is `blocked`; do not proceed to Stage 4 until cleanup passes.

## Browser confirmation

After the final automated report passes:

- Open the retained or selected Stage 3 pilot session if one remains for evidence, or create a fresh controlled character session.
- Confirm Character Mode shows the expected Maya profile.
- Confirm read and write memory are both enabled for the pilot.
- Save an explicit memory and confirm it appears under the Maya character owner.
- Send an inference-shaped ordinary message and confirm it appears as a pending suggestion, not active memory.
- Approve one suggestion, refresh active memory, and confirm it becomes selectable only after refresh.
- Reject one suggestion and confirm it remains excluded.
- Confirm a System Assistant session and an Alex character session do not display Maya records.

Record content-free pass/fail observations in `stage-3-rehearsal-results.md`.

## Rollback

To return to the Stage 2 posture:

```text
read_memory=true
write_memory=false
shared_memory_access=none
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
```

For a broader Character memory rollback, set `OMNIX_CHARACTER_MEMORY_ENABLED=0` and restart. Previously approved character memory remains stored and isolated unless explicitly forgotten.

## Exit criteria

Advance to Stage 4 shared-memory work only when:

- the Stage 3 final report is `pass`;
- browser confirmation is complete;
- explicit writes land only on the active character owner;
- write-only mode writes while reading no prior memory;
- pending suggestions are excluded until approval and refresh;
- rejected suggestions remain excluded;
- retries do not create duplicate pending candidates;
- System Assistant and other-character owners remain untouched;
- synthetic Stage 3 records, resolved candidate rows, and temporary sessions are cleaned up successfully.
