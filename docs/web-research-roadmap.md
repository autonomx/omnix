# Web Research Roadmap

Status: WSR-0 through WSR-13 implemented; final pull-request verification required on the exact head.

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
- The canonical request field is `web_research_mode`; canonical values are `disabled`, `quick`, and `deep` only.
- Retired server aliases are outside the canonical model, emit warnings and telemetry, and can be disabled with `OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED=0`. Their planned removal date may be exposed through `OMNIX_RESEARCH_LEGACY_ALIAS_SUNSET`.
- Browser compatibility mirrors, Automatic/Manual execution semantics, and manual one-turn arming state are removed.
- DuckDuckGo Instant Answer is identified as a limited keyless fallback, not comprehensive web search.
- Source identity and retrieval state are separate. `ResearchSource` is stable provenance; `ResearchSourceSnapshot` is one versioned search or extraction observation.
- Durable source IDs are separate from human citation labels such as `S1`.
- Hermes receives a dedicated declarative research planning schema and no general Omnix tool catalog. Omnix validates and executes every operation.
- Final synthesis normally receives structured evidence, limited quotations, source metadata, conflicts, and limitations rather than arbitrary full page text.
- Structured synthesis is preferred. Quick Search retains a citation-constrained plain-text fallback when a provider emits invalid structured output.
- Quick and Deep use one shared outbound-web policy for URL validation, DNS and redirects, response limits, MIME validation, TLS, and extraction.

## Completed phase sequence

- [x] WSR-0 — Contracts, ownership, precedence, and compatibility
- [x] WSR-1 — Composer, central default, and session persistence
- [x] WSR-2A — Quick Search execution
- [x] WSR-2B — Canonical sources and snapshots
- [x] WSR-3 — Shared outbound-web and extraction policy
- [x] WSR-3C — Quick Search evidence and citations
- [x] WSR-4 — Durable Deep Research jobs
- [x] WSR-5 — Dedicated research planner
- [x] WSR-6 — Iterative executor
- [x] WSR-7 — Structured Deep Research synthesis
- [x] WSR-8 — Progress and research-details UI
- [x] WSR-9 — Cache, limits, privacy, and retention
- [x] WSR-10 — Advanced Settings integration
- [x] WSR-11 — Evaluation and adversarial gates
- [x] WSR-12 — Controlled rollout
- [x] WSR-13 — Compatibility retirement

## Production gates

The completed implementation includes:

- one logical Quick Search query with bounded transport retries and a total deadline;
- Brave, Tavily, and explicitly limited DuckDuckGo Instant Answer provider semantics;
- canonical source records, snapshots, stable source IDs, and separate citation labels;
- shared outbound-web SSRF, DNS-rebinding, redirect, size, MIME, and extraction controls;
- structured Quick and Deep citations with visible fallback validation;
- durable Deep Research jobs with cancellation, checkpoints, resume, partial completion, and normal chat persistence;
- dedicated local and Hermes planning schemas with post-parse budget enforcement;
- evidence, conflict, limitation, source, and progress UI;
- centralized provider, budget, cache, retention, diagnostics, and capability settings;
- deterministic adversarial fixtures for provider degradation, SSRF, redirects, prompt injection, citations, structured output, cancellation, resume, privacy, and partial results;
- deterministic rollout cohorts, master rollback, separate Quick/local-Deep/Hermes releases, and explicit downgrade consent;
- compatibility telemetry and a server-controlled alias sunset.

Deep Research production rollout remains controlled by the WSR-12 release policy and the Settings Control Center Deep Research enablement flag.
