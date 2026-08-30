# Semantic Routing v2

## Architecture rule

**LLM parses the task. Omnix compiles the authority.**

Natural-language meaning is not an authority source. The semantic parser may
describe subjects, requested operations, data dependencies, autonomy, multi-step
structure, and ambiguity. It cannot select an Agent profile, capability, evidence
source class, trust floor, fallback policy, approval policy, or tool.

The latest user message is authoritative. Canonical Chat context (approved
memory, session summary, recent turns, and retrieved history) is reference-only
and exists only to resolve omitted subjects and references such as "it" or
"that issue".

## Production flow

1. Syntax-only deterministic fast path:
   - explicit `/agent`
   - exact supported Direct command
   - exact registered Workflow
   - explicit Quick/Deep research mode
   - trivial casual/empty turns
2. All other meaningful natural language is parsed by `SemanticTask v2`.
3. `compile_semantic_task()` deterministically derives:
   - Chat vs Agent
   - Agent profile
   - coarse action intents
   - evidence requirements and runtime policy
   - ambiguity/anomaly gates
4. `compile_task_authority()` converts those actions/evidence requirements into
   least-privilege local/external capabilities and applies explicit user
   prohibitions.
5. The durable runtime validates the compiled RunSpec again before execution.

## SemanticTask v2

The model returns semantic facts only:

- `intent`
- `subjects[]`
- `operations[]`
- `data_dependencies[]`
- `autonomous`
- `multi_step`
- `ambiguity`
- `candidate_interpretations[]`
- `confidence` (telemetry only)
- `reason_code`

`profile_id`, capability IDs, source classes, trust/fallback policy, and tool
names are intentionally absent from the model contract.

## Ambiguity and failure behavior

`confidence` is not a security boundary.

- `ambiguity=none`: compile normally.
- `ambiguity=resolvable_from_context`: compile normally because the parser
  resolved the reference using canonical Chat context.
- `ambiguity=clarification_required`: do not grant stateful authority.
- Cross-profile or subject/operation disagreements are compiler anomalies and
  fail closed rather than being silently repaired.

If the semantic parser is unavailable, Omnix may still execute an exact
syntax-level Direct/Workflow command. Ordinary harmless Chat can remain Chat.
A natural-language request that may imply stateful Agent authority is not
regex-guessed; Omnix asks for clarification instead.

## Evidence policy

The parser says what current/private information the task depends on. Omnix
maps that dependency to evidence policy. Examples:

- current repository CI -> `repo_ci_state` -> authoritative, fail closed
- physical home state -> `home_state` -> authoritative, fail closed
- current mailbox state -> `email_state` -> authoritative, fail closed
- weather -> `weather_state` -> authoritative, fail closed
- current market quote -> `market_quote` -> authoritative, fail closed
- current public web fact -> `general_current_web` -> reputable, fallback allowed

The LLM does not choose trust floors or fallback rules. Parser-resolved subject
references are bound into the deterministic evidence requirement, so a
contextual request such as "what about it?" cannot be satisfied by a receipt
for a different security. Subject-sensitive requirements that cannot be
resolved fail closed.

Bounded evidence-required Chat reads are executed through the same governed
read-only capability gate before the normal Chat provider is allowed to answer.
The resulting receipts are evaluated for subject, freshness, and trust, then
the verified output is appended to the Chat context. If required evidence is
unavailable or fails evaluation, Chat returns a governed evidence failure
instead of answering from model memory.

## Least privilege

Semantic operations are compiled without text-domain guessing in v2. Explicit
prohibitions remain deterministic hard constraints.

Examples:

- `send(email)` grants send authority, not inbox-read authority, unless the
  task also depends on mailbox state.
- `create(calendar)` grants event creation, not availability-read authority,
  unless availability is a stated data dependency.
- workspace mutation grants the coding write/test set and requires diff +
  validation acceptance.
- smart-home mutation remains bound to current home-state evidence.

## Migration and shadow mode

Production AUTO routing defaults to
`OMNIX_AGENT_SEMANTIC_ROUTING_MODE=shadow` while the v2 behavior matrices and
disagreement telemetry are being validated. Explicit test/extension parsers can
exercise v2 directly, and operators may opt in with
`OMNIX_AGENT_SEMANTIC_ROUTING_MODE=v2`.

Shadow mode keeps the legacy v1 classifier/deterministic merger as the
production result while SemanticTask v2 runs for comparison. Every typed turn
records routing comparison metadata across lane, profile, semantic actions, and
evidence domains. Promotion to v2 should happen only after those disagreements
have been reviewed and the exact-head runtime gates are green.

Legacy semantic regexes remain temporarily for:
- shadow diagnostics/rollback,
- compatibility tests/extensions,
- one-way risk detection during parser outages.

They must not grant new v2 stateful authority.

After the live semantic behavior matrices are stable, the legacy semantic
vocabularies in `router.py`, `profiles.py`, `semantic_classifier.py`, and
semantic portions of `evidence.py` can be deleted incrementally.

## Parser performance

The v2 structured contract caps output at 420 tokens and uses at most two
provider calls. A context-sensitive bounded cache keys on:

- parser version
- provider/model
- latest message
- routing-context digest
- active-objective digest
- domain-schema version

This makes retries/reloads inexpensive without incorrectly caching a phrase
such as "fix it" across different conversational contexts.

## Observability

Agent chat metadata exposes:

- `semantic_task`
- `semantic_compilation`
- `routing_shadow`

The Agent card shows a **Routing & compiler** section with the semantic reason,
compiled domain/actions, legacy-v2 comparison, and compiler anomalies. Reference
context itself is not displayed.

## Composite requests

Full multi-profile TaskGraph execution is intentionally deferred. SemanticTask
v2 detects a request that spans multiple profiles and returns a compiler anomaly
instead of silently widening one profile.

The next architecture phase can convert those semantic operations into a
deterministic TaskGraph with explicit dependency, approval, and subagent
boundaries.
