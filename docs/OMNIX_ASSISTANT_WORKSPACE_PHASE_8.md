# Omnix Assistant Workspace Phase 8 — Auditability and Provenance

Phase 8 adds lightweight response audit contracts for the assistant workspace foundation.

## Scope

- Record the provider/model and assistant identity used for a response.
- Preserve the context sources that shaped the response.
- Provide deterministic summaries for audit and context-inspection UI.

## Acceptance criteria

- Response audits can be created without mutating the caller's source list.
- Audit summaries expose source counts, source types, token totals, and latency.
- Context sources can be rendered as compact explanation rows.
