# Chat memory rollout — Stage 5 long-session compaction pilot

Status: rollout slice.

## Goal

Stage 5 enables durable long-session compaction after SQLite Chat storage, approved memory, pending suggestions, and scoped historical recall have been verified.

Enable:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
OMNIX_CHAT_COMPACTION_ENABLED=1
```

Keep disabled:

```bash
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

The default compaction threshold is 40 messages and can be changed with `OMNIX_CHAT_COMPACTION_THRESHOLD`. The prompt keeps the most recent 24 user/assistant messages after a verified summary is available.

## Safety boundary

Compaction never rewrites or deletes authoritative Chat messages. Once a session reaches the configured threshold, Omnix enqueues an idempotent `assistant.history.compact` CPU job. The job stores a versioned summary with an explicit through-message boundary and source-message count.

Prompt assembly uses the summary only after it has been persisted successfully. While a job is pending, missing, stale, or unsuccessful, the complete current-session transcript remains available. Conversation summaries are contextual aids, not approved curated memory.

## Preflight command

Run before enabling compaction:

```bash
python scripts/chat_memory_stage5_preflight.py
```

The temporary-store rehearsal validates:

- sessions below the threshold create no compaction job;
- a long session creates one durable job and enqueue retries reuse it;
- the job uses the expected through-message boundary;
- before processing, prompt assembly retains the complete session history;
- processing persists a versioned summary and completes the job with a summary output reference;
- deterministic summary content records durable decisions and unresolved items;
- after persistence, prompt assembly renders the summary plus exactly the most recent 24 messages;
- disabling compaction restores full-history prompt behavior;
- Hermes remains disabled.

The rehearsal uses temporary Chat, memory, summary, and job SQLite databases. It does not read or mutate production stores.

## Pilot checklist

1. Complete Stage 1 through Stage 4 verification.
2. Run `python scripts/chat_memory_stage5_preflight.py`.
3. Confirm `ok: true`.
4. Enable `OMNIX_CHAT_COMPACTION_ENABLED=1`.
5. Keep Hermes disabled.
6. Use the default threshold initially unless a lower threshold is required for a controlled pilot.
7. Grow one session past the threshold and confirm exactly one pending compaction job appears for its boundary.
8. Confirm Chat retains full history until the summary is persisted.
9. Process the job and confirm the session prompt uses one summary plus the most recent 24 messages.
10. Confirm recent turns, durable decisions, and unresolved items remain represented.
11. Disable compaction and confirm ordinary Chat returns to full current-session history.

## Rollback

Disable compaction and restart:

```bash
OMNIX_CHAT_COMPACTION_ENABLED=0
```

Stored summaries and authoritative Chat messages remain intact, but prompt assembly stops using summaries and returns to the complete current-session transcript. SQLite Chat, curated memory, suggestions, and historical recall remain independently controlled.

## Advancement criteria

Move to Stage 6 only after:

- threshold and idempotency behavior are stable;
- pending or failed compaction never drops current-session context;
- persisted summaries use explicit, correct through-message boundaries;
- prompt assembly retains exactly the configured recent-message window;
- summaries remain separate from approved memory;
- rollback restores full-history prompts without data loss;
- no summary or job duplication appears across retries and restarts.
