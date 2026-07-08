# Chat memory rollout — Stage 1 SQLite storage preflight

Status: rollout slice.

## Goal

Stage 1 turns the completed MEM-0 through MEM-15 implementation into a safe production rollout path. The only feature intended to be enabled in this stage is SQLite-backed Chat storage:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
```

All memory-capability flags should remain off until their own staged rollout gates pass:

```bash
OMNIX_CHAT_MEMORY_ENABLED=0
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

## Why SQLite first

The memory system depends on durable session/message identity, stable restart behavior, and non-destructive migration from the legacy JSON Chat store. Enabling SQLite storage first validates those foundations without changing prompt inputs, creating memory candidates, searching prior conversations, compacting transcripts, or synchronizing Hermes files.

## Preflight command

Run the read-only rollout preflight before setting `OMNIX_CHAT_SQLITE_STORE_ENABLED=1`:

```bash
python scripts/chat_memory_stage1_preflight.py
```

The preflight reports:

- legacy JSON Chat store path and byte size;
- SQLite Chat database path;
- whether the SQLite schema can initialize;
- whether a legacy JSON import can validate all sessions/messages;
- session and message counts after a temporary migration rehearsal;
- which memory-related runtime flags are currently enabled.

The rehearsal uses a temporary SQLite database and does not modify the production SQLite database or the legacy JSON file.

## Rollout checklist

1. Stop the app cleanly.
2. Back up `resources/data/omnix_chat_sessions.json` if present.
3. Run `python scripts/chat_memory_stage1_preflight.py`.
4. Confirm the preflight reports `ok: true`.
5. Set `OMNIX_CHAT_SQLITE_STORE_ENABLED=1`.
6. Keep every memory-capability flag disabled.
7. Start the app and open the Chat UI.
8. Verify existing sessions are visible.
9. Send one ordinary Chat message.
10. Restart the app and verify the new message remains visible.
11. Keep the JSON backup until at least one clean restart cycle is verified.

## Rollback

Unset the SQLite flag and restart:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=0
```

The legacy JSON file is preserved by the migration path and remains the rollback artifact. Do not delete it during Stage 1.

## Advancement criteria

Move to Stage 2 only after:

- Stage 1 preflight passes on the target machine;
- SQLite storage survives at least one clean restart;
- ordinary Chat prompt behavior is unchanged with memory flags off;
- no migration or persistence errors appear in logs;
- rollback to JSON has been tested or the JSON backup is confirmed intact.
