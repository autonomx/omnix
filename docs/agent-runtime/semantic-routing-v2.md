# Semantic Routing v2

## Architecture rule

**LLM parses the task. Omnix compiles the authority.**

Natural-language meaning is not an authority source. The semantic parser may
describe subjects, requested operations, data dependencies, autonomy, multi-step
structure, and ambiguity. It cannot select an Agent profile, capability, evidence
source class, trust floor, fallback policy, approval policy, or tool.

The latest user message is authoritative. Routing also receives two explicitly
separated reference/state inputs:

- **Current environment**: current-turn facts such as the attached Local folder,
  selected workspace, and attachment kinds. Environment state can resolve
  feasibility and references, but does not grant action authority.
- **Active objective**: the canonical user-authored request, profile/domain,
  status, blocking reason, and related run/workspace identity for the current
  unfinished objective. It is reference-only and never authorizes continuation
  by itself.

Canonical Chat context (approved memory, session summary, recent turns, and
retrieved history) remains reference-only and exists only to resolve omitted
subjects and references such as "it", "that issue", or "try again".

## Production flow

1. Syntax-only deterministic fast path:
   - explicit `/agent`
   - exact supported Direct command
   - exact registered Workflow
   - explicit Quick/Deep research mode
   - trivial casual/empty turns
2. All other meaningful natural language is parsed by `SemanticTask v2`.
3. `normalize_semantic_task()` canonicalizes Omnix's ontology without guessing
   new user intent or granting authority.
4. `compile_turn_plan()` receives the normalized SemanticTask plus the current
   ActiveObjective and RoutingEnvironment and produces the single final TurnPlan:
   - continuity relation and disposition
   - effective user-authored request
   - Chat vs Agent
   - Agent profile
   - coarse action/authority delta
   - evidence requirements and runtime policy
   - start/steer/clarify disposition
5. `compile_task_authority()` converts the TurnPlan's actions/evidence
   requirements into least-privilege local/external capabilities and applies
   explicit user prohibitions.
6. Durable Agent steering calls the same TurnPlan compiler before creating a
   TaskRevision or superseding run. The durable runtime validates the resulting
   authority again before execution.

## SemanticTask v2

The model returns semantic facts only:

- `intent`
- `subjects[]`
- `operations[]`
- `data_dependencies[]`, including `retrieval_mode` for external reads:
  - `lookup`: fetch a known subject/value/artifact
  - `verify`: check a fixed set of known claims/artifacts
  - `filter`: apply current facts to a fixed candidate set
  - `discover`: search an unknown result/source set
- `autonomous` (descriptive only; not a lane switch)
- `multi_step` (descriptive/compatibility only; not a public-read lane switch)
- `objective_relation`
- `request_completeness` (`self_contained` or `context_dependent`)
- `replay_target` (`latest_authoritative` or `base_objective`; meaningful only for context-dependent resume)
- `ambiguity`
- `candidate_interpretations[]`
- `confidence` (telemetry only)
- `reason_code`

`profile_id`, capability IDs, source classes, trust/fallback policy, and tool
names are intentionally absent from the model contract.

Target semantics are generic rather than feature-specific. `workspace`/`repository`
mean project files, `repository_ci` means CI state, and `operations` means
local service/process diagnostics or controlled operational commands that do not
edit project files. With a Local folder attached, requests to change the selected
app/project/UI are represented as workspace/repository operations rather than
`conversation`; exact source paths are discovered inside the workspace and are
not embedded in production routing rules.

## TurnPlan and semantic normalization

`SemanticTask` is intentionally not the final routing result. Semantic output
first passes through a deterministic ontology normalizer that may deduplicate
equivalent operations/dependencies and enforce schema-level invariants such as
response-only explanation remaining non-authoritative. It does not use
application keywords to infer a different domain.

`TurnPlan` is the one final routing contract for natural-language turns. It
contains:

- `relation`: none / continue / resume / revise
- `disposition`: new objective / continue / revise / replay / response-only continuation
- `latest_request`: exact latest user-authored text
- `effective_request`: exact user-authored text handed across the execution boundary
- final lane and profile
- coarse authority delta / action intents
- evidence policy
- active run action: Chat, start Agent, steer Agent, or clarify

A discourse relation is not an execution instruction. `request_completeness`
describes whether the latest message contains its own requested action/target or
must recover that action from the prior objective. For a genuinely opaque
resume, `replay_target` semantically identifies whether the user means the
latest authority-bearing instruction or the original/base objective. In
particular, `resume` does **not** mean "replace the latest message with old
text." An opaque
request such as "try that exact request again" may have
`disposition=replay_objective`, while a self-contained request such as
"run the focused test again" remains authoritative as written.

Response-only continuations of an active Agent objective are decided inside the
TurnPlan compiler. There is no second post-hoc Chat-to-Agent promotion policy.

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
When the latest turn is referential and an unfinished ActiveObjective exists,
Omnix retries semantic parsing once with a bounded recent-context projection
plus the separate objective/environment state. If that retry also fails, the
turn fails closed instead of silently falling through to legacy Chat routing.
When parser output is unavailable, a deny-only deterministic risk detector may
block requests that appear to require stateful/private execution authority. That
detector is not a router: it cannot select a profile, capability, evidence
policy, or tool, and therefore cannot grant new authority. Harmless response-only
Chat proceeds to the configured conversational provider with
`authority_granted=false`; referential turns with an unfinished ActiveObjective
and execution-risk turns still fail closed.

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

The execution scheduler consumes the canonical retrieval shape rather than the
parser's fuzzy `multi_step` or `autonomous` booleans:

- `lookup`, `verify`, and `filter` are bounded governed Chat reads.
- `discover` is durable Agent research because the result/source set is unknown
  before retrieval.
- Evidence requirements are the canonical source of external read authority.
  The parser does not need to duplicate a dependency as a `research_read` or
  `market_read` action merely to authorize retrieval.
- Findings already gathered/confirmed by the active conversation are reusable
  context. A later turn that combines those findings with a new bounded lookup
  retrieves only the genuinely new information unless the user explicitly asks
  to recheck, refresh, update, or verify the prior finding again.
- Remote CI inspection is represented separately as `repo_ci_read`; it does
  not imply local `workspace_execute` authority. `repository_ci` is limited
  to code-repository CI/CD checks, workflows, jobs, builds, and logs. Public
  service health/status pages, outages, and vendor incidents are `public_web`;
  the semantic normalizer conservatively repairs an explicit public-service
  incident mislabeled as repository CI.
- A conceptual/meta question about why a prior action needed authority remains
  ordinary Chat when it is detached from the active objective's deliverable.
- A pure response-only request to summarize, synthesize, rank, or reformat
  findings from an active Agent remains an Agent continuation when it needs no
  fresh authority.
- If that continuation also requires a bounded `lookup`, `verify`, or
  `filter` evidence read, the bounded Chat scheduler takes precedence. It is
  no longer response-only work, and an active Agent must not pull it back across
  the Agent boundary merely because `objective_relation=continue`.

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
- `operations` targets compile to the `ops` profile for local service/process
  diagnostics and controlled commands; inspect/read receives workspace read plus
  controlled command authority, while execute/validate additionally receives
  test authority. The profile never receives workspace edit/write authority.
- smart-home mutation remains bound to current home-state evidence.

## Production routing

The retrieval scheduler is the v3 execution boundary layered on SemanticTask
v2: semantic facts are normalized into a canonical authority/evidence plan
before Chat-versus-Agent scheduling. This absorbs equivalent LLM decompositions
before they reach the safety or execution boundary.

SemanticTask v2 plus the deterministic compiler is the sole production
authority for natural-language meaning. The former
`OMNIX_AGENT_SEMANTIC_ROUTING_MODE` switch and its `shadow`/legacy-v1
production path have been removed; inherited environment variables cannot
change the production router.

Explicit command syntax remains a deterministic fast path. Compatibility
adapters may convert injected test/extension classifier output into a
SemanticTask, but they do not select a separate production router. Provider
selection for SemanticTask v2 is capability/interface based: any provider
registered through the trusted Omnix `BaseProvider` registry can use the shared
structured-output gateway. There is no second hard-coded semantic-parser
provider allowlist.

## Parser performance

The v2 structured contract caps output at 420 tokens and uses at most two
provider calls. A context-sensitive bounded cache keys on:

- parser version
- provider/model
- latest message
- routing-context digest
- active-objective digest
- current-environment digest
- domain-schema version

This makes retries/reloads inexpensive without incorrectly caching a phrase
such as "fix it" across different conversational contexts.

Semantic parsing is also request-scoped. The Chat routing boundary derives one
absolute monotonic deadline from the selected provider's configured turn
timeout and passes the remaining budget to SemanticTask v2. The same deadline
is retained for the eventual ordinary Chat provider call. Operators may still
set `OMNIX_AGENT_SEMANTIC_TASK_PARSER_TIMEOUT_SECONDS` for an explicit parser
budget; when no provider timeout is available, the structured gateway's
provider-independent safety budget is used. There is no provider-specific
20-second Codex parser timeout.

## Observability

Agent chat metadata exposes:

- `semantic_task`, including `objective_relation` and `request_completeness`
- `turn_plan`, including final lane/profile, continuity disposition, effective request, run action, and authority delta
- `semantic_compilation`
- `routing_decision`, including `production_router` and `production_lane`
- `active_objective`
- `routing_environment`

The Agent card shows a **Routing & compiler** section with the semantic reason,
compiled domain/actions, the production lane, and compiler anomalies. Reference
context itself is not displayed.

## Composite requests

SemanticTask v2 still detects cross-profile meaning as
`unsupported_composite_profiles`; that anomaly is never repaired by widening a
single Agent profile. The TurnPlan boundary now treats that exact, otherwise
unambiguous anomaly as a request for the deterministic multi-profile TaskGraph
compiler.

TaskGraph compiles each profile-bound subtask independently through the existing
semantic/evidence/authority compilers. Each node receives its own capability,
resource, evidence, approval, acceptance, and budget envelope. The coordinator
does not receive the union of node capabilities.

Other semantic compiler anomalies remain fail closed. Ambiguous composite turns
still require clarification.

See `docs/agent-runtime/task-graph-phases-15-19.md` for evidence coverage,
graph scheduling, steering/recovery, and optimization semantics.


## Conversational task continuity

ActiveObjective is deliberately separate from generic memory and is now
structured rather than primarily represented as a flattened string. It stores:

- the base user-authored request
- ordered user-authored revision entries
- relation + continuity disposition for each revision
- run/profile/workspace identity and objective status
- a compatibility `canonical_request` projection for older metadata consumers

The structured record derives the latest user request and an effective objective
projection without parsing a concatenated transcript. Assistant prose is never
stored as objective authority.

The semantic parser supplies only
`objective_relation=none|continue|resume|revise`. The TurnPlan compiler decides
whether that relation means new work, additive steering, revision, opaque replay,
or a response-only continuation. Replay is allowed only when the latest
user-authored command delegates its action text to prior context. Complete
commands remain authoritative as written.

Regex normalization is limited to unambiguous safety/discourse markers; it does
not select a lane, profile, tool, evidence source, or capability.

## Test architecture

Routing tests are split by responsibility:

1. Semantic/parser tests validate meaning and allowed semantic equivalence.
2. Deterministic TurnPlan tests require exact lane/profile/disposition/effective
   request/evidence outcomes for SemanticTask + ActiveObjective + Environment.
3. Live multi-turn Luna tests validate end-to-end invariants: no authority
   widening, correct evidence/authority domain, exact user-authored handoff,
   correct start/steer behavior, no stale objective replay, and no assistant
   prose entering authority. Chat-versus-Agent is a hard gate only when the
   scheduler changes execution semantics (discovery, stateful/private/local
   execution, mutation, replay). For bounded external reads and zero-authority
   response continuations, the scenario lane/profile are optimization
   preferences; equivalent schedules are recorded as preference misses instead
   of correctness failures.

The live matrix consumes the production TurnPlan compiler and follows the
actual compiled lane through subsequent turns rather than manufacturing the
fixture's preferred ActiveObjective. This prevents a safe bounded-Chat choice
from causing artificial continuity failures later in the scenario.
