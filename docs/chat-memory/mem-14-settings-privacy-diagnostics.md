# MEM-14 — Settings, privacy, and diagnostics

Status: implementation complete pending exact-head required checks.

Omnix now uses one persisted server-side settings model for curated-memory injection, pending suggestions, historical recall, long-session compaction, Hermes synchronization, token budgets, retention, and user-visible memory indicators. Environment variables remain supported as explicit deployment overrides and are reported as locked controls in the UI.

Inferred memory approval is permanently required by policy and cannot be disabled through the settings API. The settings and diagnostics response is content-free: it reports feature state, budgets, override sources, and privacy policy without exposing memory records, candidate text, historical excerpts, or hidden prompt content.

The Memory view provides independent toggles for each capability. Enforcement occurs in backend selection, job enqueue, retrieval, compaction, and Hermes adapter paths rather than relying on frontend visibility.
