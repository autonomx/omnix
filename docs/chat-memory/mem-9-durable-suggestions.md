# MEM-9 — Durable pending memory suggestions

Status: implementation complete pending exact-head required checks.

Post-turn suggestion extraction is feature-gated by `OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED` and queued through the shared durable SQLite job store. Job creation uses a deterministic session/message idempotency key, and candidate persistence uses the existing source-message/fingerprint uniqueness constraint.

The initial extractor is deterministic and deliberately narrow. It recognizes explicit stable preference, instruction, and personal-environment fact patterns while rejecting URLs, external instruction markers, credentials, secrets, and temporary chatter. Results are always pending candidates; they never enter prompt selection before approval.

Recognized explicit memory commands are excluded from suggestion extraction because their mutations are already handled synchronously by MEM-8.
