# MEM-11 — FTS5 historical retrieval

Status: implementation complete pending exact-head required checks.

Historical recall is independently feature-gated by `OMNIX_CHAT_HISTORY_RECALL_ENABLED`. The service creates and rebuilds a local FTS5 index from authoritative SQLite Chat rows, applies profile/workspace/project scope before returning results, excludes the active session, and respects bounded result limits.

If FTS5 or its backing Chat schema is unavailable, recall reports a degraded status and returns no excerpts without failing ordinary Chat or curated memory. Rebuilding from authoritative rows ensures deleted sessions disappear from retrieval.

Retrieved excerpts enter the typed historical-conversation section of `PromptAssembly`; they are never presented as approved curated memory and are labelled potentially stale.
