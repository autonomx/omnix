# MEM-7 — Memory management API and UI

Status: implementation complete pending exact-head required checks.

This phase adds server-scope-bound memory CRUD, candidate review, optimistic revisions, a typed browser client, and a functional Memory view. New approved records remain outside an active frozen session snapshot until the user explicitly refreshes it. Forget operations continue to purge active snapshot copies immediately.

The management and session snapshot routes remain internal to the handwritten client in this phase and are excluded from the generated public OpenAPI contract.
