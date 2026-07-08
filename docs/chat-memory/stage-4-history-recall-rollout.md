# Chat memory rollout — Stage 4 scoped history recall pilot

Status: rollout slice.

## Goal

Stage 4 enables bounded, scope-first historical Chat recall after SQLite Chat storage, approved memory, and pending suggestions have been verified.

Enable:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
```

Keep disabled:

```bash
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

## Safety boundary

Historical excerpts are conversation context, not approved curated memory. Retrieval applies backend-owned profile, workspace, and project scope before ranking, excludes the active session, limits the number of returned messages, and labels rendered excerpts as potentially stale earlier-conversation material.

The index is rebuilt from authoritative SQLite Chat rows. Deleted sessions therefore disappear from later searches. If FTS5 or the Chat schema is unavailable, normal Chat continues with an empty retrieved-history section and content-free degraded diagnostics.

## Preflight command

Run before enabling history recall:

```bash
python scripts/chat_memory_stage4_preflight.py
```

The temporary-store rehearsal validates:

- matching messages from an earlier same-scope session are retrieved;
- messages from another project are excluded before ranking;
- the active session is excluded from historical results;
- retrieved excerpts render under the earlier-conversation section, never the approved-memory section;
- deleting a session and rebuilding the index removes its messages;
- disabling the history flag restores empty-history behavior;
- unavailable FTS5 degrades to zero excerpts without failing prompt assembly;
- compaction and Hermes remain disabled.

The rehearsal uses temporary Chat and memory SQLite databases. It does not read or mutate production stores.

## Pilot checklist

1. Complete Stage 1 through Stage 3 verification.
2. Run `python scripts/chat_memory_stage4_preflight.py`.
3. Confirm `ok: true` and `history_status.available: true`.
4. Enable `OMNIX_CHAT_HISTORY_RECALL_ENABLED=1`.
5. Keep compaction and Hermes disabled.
6. Create two sessions in the same project with a distinctive non-sensitive topic.
7. Ask about that topic from the newer session and confirm bounded earlier-session excerpts appear.
8. Confirm another project containing the same terms is never retrieved.
9. Delete the earlier session and confirm its excerpts disappear.
10. Disable history recall and confirm ordinary Chat still works with no historical section.

## Rollback

Disable history recall and restart:

```bash
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
```

The FTS index and SQLite transcripts remain intact, but prompt assembly stops querying or rendering historical excerpts. Approved memory and pending suggestions remain independently controlled by their own flags.

## Advancement criteria

Move to Stage 5 only after:

- no cross-profile, cross-workspace, or cross-project leakage is observed;
- the active session is never returned as historical context;
- deleted sessions disappear after index synchronization;
- retrieved history remains visibly separate from approved memory;
- degraded or disabled history recall cannot fail ordinary Chat;
- result counts and rendered excerpts remain bounded.
