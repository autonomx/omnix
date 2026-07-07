# Web Research Roadmap

Status: canonical implementation source of truth

## Product modes

- `disabled`: no external research request.
- `quick`: one bounded logical search query for the submitted turn.
- `deep`: a durable staged research job with evidence, conflicts, citations, cancellation, and resume.

## Mode resolution

Resolve in this order:

1. explicit per-turn override;
2. backend-persisted conversation override;
3. Settings Control Center profile default;
4. `disabled` fallback.

Malformed values resolve to `disabled`. Runtime feature availability is applied after precedence. An unavailable requested mode never runs silently. Deep Research may downgrade to Quick Search only when the request explicitly allows it and the response carries a visible warning.

## Architectural invariants

- Deep Research uses the shared job statuses and research-specific stages. It does not add global job statuses or a combined CPU/network resource class.
- Stage resource classes reflect the actual runtime: CPU for deterministic work, NETWORK for search or remote model calls, and the appropriate GPU class for local models.
- Deep Research begins with `begin_user_message`, creates and returns a durable job, then persists a normal assistant message later.
- A partial result completes the shared job with `output.research_status = partial` and persists a readable assistant message with job and source-manifest metadata.
- Profile defaults belong to the settings API. Conversation overrides belong to the backend chat session. Turn overrides belong to the request. Runtime state is read-only. Credentials remain environment or integration owned.
- Compatibility accepts `web_search_mode` and `web_research_mode` for one release. `automatic` and `manual` normalize to `quick`; unknown values normalize to `disabled`.
- DuckDuckGo Instant Answer is identified as a limited keyless fallback, not comprehensive web search.
- Source identity and retrieval state are separate. `ResearchSource` is stable provenance; `ResearchSourceSnapshot` is one versioned search or extraction observation.
- Durable source IDs are separate from human citation labels such as `S1`.
- Hermes receives a dedicated declarative research planning schema and no general Omnix tool catalog. Omnix validates and executes every operation.
- Final synthesis normally receives structured evidence, limited quotations, source metadata, conflicts, and limitations rather than arbitrary full page text.
- Structured synthesis is preferred. Quick Search retains a citation-constrained plain-text fallback when a provider emits invalid structured output.
- Quick and Deep use one shared outbound-web policy for URL validation, DNS and redirects, response limits, MIME validation, TLS, and extraction.

## Phase sequence

### WSR-0 — Contracts, ownership, precedence, and compatibility

Canonical modes, precedence, settings ownership, compatibility normalization, discriminated results, source/snapshot identities, job constants, and message metadata.

### WSR-1 — Composer, central default, and session persistence

Three-mode UI, profile default, backend conversation override, turn override, exact browser migration, and removal of manual arming.

### WSR-2A — Quick Search execution

One logical query, bounded attempts, total deadline, provider adapters, coverage diagnostics, and safe failure behavior.

### WSR-2B — Canonical sources and snapshots

Stable IDs, citation labels, canonical URLs, deduplication, persistence, and source manifests.

### WSR-3 — Shared outbound-web and extraction policy

SSRF controls, DNS and redirect validation, fetch limits, content validation, readable extraction, hashes, and retention metadata.

### WSR-3C — Quick Search evidence and citations

Structured evidence, structured answer path, plain-text fallback, citation validation, persisted manifests, and source UI.

### WSR-4 — Durable Deep Research jobs

Shared job lifecycle, research stages, non-blocking chat flow, checkpoints, cancellation, resume, and partial assistant-message persistence.

### WSR-5 — Dedicated research planner

Dedicated Hermes schema and method, no general tool catalog, deterministic fallback, and post-parse budget enforcement.

### WSR-6 — Iterative executor

Bounded search/extract/evaluate loop, evidence and conflict records, stop conditions, and resume.

### WSR-7 — Structured Deep Research synthesis

Evidence-linked facts, inferences, limitations, recommendations, citation validation, conflicts, and partial completion.

### WSR-8 — Progress and research-details UI

Stage progress, refresh recovery, cancellation, source/snapshot details, conflicts, warnings, and accessibility announcements.

### WSR-9 — Cache, limits, privacy, and retention

Search and extraction caches, limits, privacy boundaries, expiry, and cleanup.

### WSR-10 — Advanced Settings integration

Provider, budgets, retention, runtime status, diagnostics, and capability availability.

### WSR-11 — Evaluation and adversarial gates

Provider, retry, SSRF, redirect, prompt-injection, structured-output, citation, cancellation, resume, and partial-result fixtures.

### WSR-12 — Controlled rollout

Feature flags, Quick rollout, local Deep planner rollout, Hermes rollout, explicit downgrade behavior, and rollback.

### WSR-13 — Compatibility retirement

Remove legacy request fields and modes, browser compatibility mirrors, manual-search state, and temporary migration code.

## First production milestone

Deep Research does not start until Disabled and Quick Search provide explicit precedence, central and conversation defaults, one bounded logical query, an honest provider coverage label, canonical sources and snapshots, stable citations, safe extraction, structured evidence, citation validation, plain-text fallback, diagnostics, and deterministic SSRF and prompt-injection fixtures.
