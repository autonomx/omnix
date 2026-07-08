# MEM-12 — Long-session compaction

Status: implementation complete pending exact-head required checks.

Long-session compaction is feature-gated by `OMNIX_CHAT_COMPACTION_ENABLED`. Once a session reaches the configured threshold, Omnix creates an idempotent durable `assistant.history.compact` CPU job. The processed artifact is a versioned SQLite conversation summary with an explicit through-message boundary and source-message count.

Provider prompts use a summary only after that artifact has been persisted successfully. When a verified summary exists, the summary plus the most recent 24 messages are supplied; without a summary, the complete current-session history remains available, preventing silent context loss after a failed or pending job.

Summaries are contextual aids and are not promoted to approved curated memory. Historical FTS recall remains available independently for older details.
