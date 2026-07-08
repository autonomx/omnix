# Chat memory rollout — Stage 2 explicit approved-memory pilot

Status: rollout slice.

## Goal

Stage 2 enables manual approved-memory usage after Stage 1 SQLite Chat storage has been verified. This stage allows users to save explicit memories, refresh the active Chat snapshot, and use approved snapshot memory in prompts.

Enable only:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
```

Keep disabled:

```bash
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

## Why explicit memory next

Explicit approved memory has the smallest trust surface. It depends on the already-verified SQLite Chat store, the approved-memory repository, frozen snapshots, forget invalidation, and the typed prompt assembly. It does not create inferred candidates, search old conversations, compact sessions, or touch Hermes files.

## Preflight command

Run the temporary-store preflight before enabling `OMNIX_CHAT_MEMORY_ENABLED=1`:

```bash
python scripts/chat_memory_stage2_preflight.py
```

The preflight creates temporary Chat and memory stores and validates:

- explicit memory save;
- snapshot refresh;
- approved memory selection;
- prompt assembly injection when memory is enabled;
- absence of pending candidates;
- disabled suggestions/history/compaction/Hermes flags;
- forget removal from subsequent prompt assembly.

The preflight does not read or mutate production Chat, memory, settings, Hermes, or history files.

## Pilot checklist

1. Complete Stage 1 and keep the legacy JSON rollback artifact.
2. Run `python scripts/chat_memory_stage2_preflight.py`.
3. Confirm the preflight reports `ok: true`.
4. Set `OMNIX_CHAT_MEMORY_ENABLED=1`.
5. Keep suggestions, history recall, compaction, and Hermes disabled.
6. Open the Memory view for a single pilot Chat session.
7. Save one explicit `session` or `workspace` memory.
8. Refresh active Chat memory.
9. Send an ordinary Chat message and confirm the memory-use indicator/metadata shows one selected memory.
10. Forget the memory and verify a later prompt no longer uses it.

## Rollback

Unset only the curated-memory flag and restart:

```bash
OMNIX_CHAT_MEMORY_ENABLED=0
```

Saved memory records remain in SQLite, but prompt injection stops. For data rollback, use the Memory view's Forget action or keep the SQLite memory database backup from before the pilot.

## Advancement criteria

Move to Stage 3 only after:

- explicit-memory preflight passes on the target machine;
- memory-disabled rollback has been tested;
- forget removes prompt use immediately;
- ordinary Chat behavior remains stable with suggestions/history/compaction/Hermes off;
- no unexpected pending candidates are created during the pilot.
