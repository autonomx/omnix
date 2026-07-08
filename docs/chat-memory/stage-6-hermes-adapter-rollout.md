# Chat memory rollout — Stage 6 optional Hermes adapter pilot

Status: rollout slice.

## Goal

Stage 6 optionally enables review-first synchronization with Hermes memory files after the native Omnix Chat memory stack has been verified through long-session compaction.

Enable only for a controlled pilot:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
OMNIX_CHAT_COMPACTION_ENABLED=1
OMNIX_HERMES_MEMORY_SYNC_ENABLED=1
```

Optionally select a non-default Hermes directory:

```bash
OMNIX_HERMES_MEMORY_DIR=/path/to/hermes/memories
```

Hermes remains optional. Native Omnix Chat memory is authoritative and continues to function when Hermes is disabled, missing, or offline.

## Trust boundary

The adapter recognizes only `USER.md` and `MEMORY.md`.

Import rules:

- unmanaged lines are screened for scratchpad, tool-output, execution-log, instruction-injection, and secret markers;
- managed Omnix export blocks are ignored on re-import;
- accepted lines become pending `source=hermes`, `trust_level=unverified_agent` candidates;
- imported candidates never enter prompts until a user explicitly approves them;
- repeated imports reuse the same pending candidates.

Export rules:

- only active, normal-sensitivity, user-approved, scope-compatible Omnix records are exported;
- Hermes-origin records, pending candidates, session-only records, and untrusted records are excluded;
- only the Omnix managed block is replaced;
- unmanaged Hermes text is preserved;
- writes use a temporary file followed by atomic replacement.

These rules prevent automatic trust elevation and import/export feedback loops.

## Preflight command

Run before enabling Hermes synchronization:

```bash
python scripts/chat_memory_stage6_preflight.py
```

The temporary-store rehearsal validates:

- disabled synchronization performs no import or export;
- a missing Hermes directory reports a nonfatal unavailable status;
- only safe unmanaged lines from `USER.md` and `MEMORY.md` become pending candidates;
- scratchpad content, managed blocks, tool output, injection text, and secret markers are excluded;
- repeated imports are idempotent;
- imported candidates remain inactive until approval;
- approved Hermes-origin memory is not exported back to Hermes;
- compatible user-saved global and project records are exported;
- session-only records and pending candidates are excluded;
- unmanaged Hermes text survives export;
- repeated exports are byte-for-byte idempotent;
- an unavailable write target reports a nonfatal status;
- disabling synchronization leaves native Omnix memory intact.

The rehearsal uses temporary Hermes files and a temporary SQLite memory repository. It does not read or mutate production stores.

## Pilot checklist

1. Complete Stage 1 through Stage 5 verification.
2. Back up the selected Hermes memory directory.
3. Run `python scripts/chat_memory_stage6_preflight.py`.
4. Confirm `ok: true`.
5. Enable `OMNIX_HERMES_MEMORY_SYNC_ENABLED=1` for one controlled profile/project.
6. Import and inspect every pending Hermes candidate before approval.
7. Reject ambiguous, operational, secret-bearing, or instruction-like entries.
8. Export approved compatible Omnix memory and verify unmanaged Hermes content remains present.
9. Repeat import and export to confirm no duplicates or feedback loop.
10. Disable Hermes synchronization and confirm native memory, history recall, and compaction continue normally.

## Rollback

Disable synchronization and restart:

```bash
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Disabling the adapter stops all Hermes reads and writes. Existing Omnix records, pending candidates, snapshots, Chat history, FTS recall, and compaction artifacts remain intact. Existing Hermes files are not deleted or rewritten during rollback.

## Release criteria

The optional adapter is ready only after:

- imports remain pending and reviewable;
- blocked content never creates candidates;
- exports contain only approved compatible non-Hermes records;
- unmanaged text remains present outside the managed block;
- repeated sync operations are idempotent;
- missing or unwritable Hermes storage cannot fail normal Chat;
- disabling the adapter fully stops synchronization without affecting native memory.
