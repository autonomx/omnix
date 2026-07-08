# Chat memory rollout — Stage 3 pending suggestion pilot

Status: rollout slice.

## Goal

Stage 3 enables deterministic pending-memory suggestions after SQLite Chat storage and explicit approved memory have been verified.

Enable:

```bash
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
```

Keep disabled:

```bash
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

## Safety boundary

Suggestions are review-first. A suggestion job may create a pending candidate, but that candidate is never prompt eligible until the user approves it. Approval creates a curated memory record, and an already-active Chat session still requires an explicit snapshot refresh before that record enters later provider prompts.

The deterministic extractor accepts only narrow durable patterns such as stable preferences, explicit standing instructions, and simple user-owned facts. It rejects URLs, external-context markers, prompt-injection language, credentials, secrets, and temporary chatter.

## Preflight command

Run before enabling suggestion jobs:

```bash
python scripts/chat_memory_stage3_preflight.py
```

The temporary-store rehearsal validates:

- one durable user statement creates one suggestion job;
- enqueue retries reuse the same job;
- processing retries reuse the same pending candidate;
- the candidate remains `pending`, `assistant_suggested`, and `unverified_agent`;
- pending candidates are absent from active memory and prompt assembly;
- approval alone does not alter an existing frozen snapshot;
- explicit snapshot refresh makes the approved record prompt eligible;
- external/instructional content creates no candidate;
- history recall, compaction, and Hermes remain disabled.

The rehearsal uses temporary SQLite Chat, memory, and job databases. It does not read or mutate production stores.

## Pilot checklist

1. Complete Stage 1 and Stage 2 verification.
2. Run `python scripts/chat_memory_stage3_preflight.py`.
3. Confirm `ok: true`.
4. Enable `OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1`.
5. Keep history recall, compaction, and Hermes disabled.
6. Send one durable preference such as `I prefer concise implementation summaries`.
7. Confirm exactly one pending candidate appears in the Memory view.
8. Verify the current Chat prompt does not use the pending candidate.
9. Approve the candidate.
10. Verify the current Chat still does not use it before refresh.
11. Refresh active Chat memory and verify later prompts may use it.
12. Send URL or prompt-injection-like text and confirm no candidate is created.

## Rollback

Disable suggestions and restart:

```bash
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
```

Existing pending candidates remain reviewable but no new suggestion jobs are enqueued. Curated memory remains independently controlled by `OMNIX_CHAT_MEMORY_ENABLED`.

## Advancement criteria

Move to Stage 4 only after:

- duplicate job and processing retries create no duplicate candidates;
- pending content never appears in prompts;
- user approval remains mandatory;
- snapshot refresh remains explicit;
- risky or external content is rejected;
- disabling suggestions stops new jobs without affecting ordinary Chat.
