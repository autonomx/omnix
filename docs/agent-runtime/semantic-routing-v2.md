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

Target semantics are generic rather than feature-specific. `workspace`/`repository`
mean project files, `repository_ci` means CI state, and `operations` means
local service/process diagnostics or controlled operational commands that do not
edit project files. With a Local folder attached, requests to change the selected
app/project/UI are represented as workspace/repository operations rather than
`conversation`; exact source paths are discovered inside the workspace and are
not embedded in production routing rules.

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

- `semantic_task`, including `objective_relation` (`none`, `continue`, `resume`, or `revise`)
- `semantic_compilation`
- `routing_decision`, including `production_router` and `production_lane`
- `active_objective`
- `routing_environment`

The Agent card shows a **Routing & compiler** section with the semantic reason,
compiled domain/actions, the production lane, and compiler anomalies. Reference
context itself is not displayed.

## Composite requests

Full multi-profile TaskGraph execution is intentionally deferred. SemanticTask
v2 detects a request that spans multiple profiles and returns a compiler anomaly
instead of silently widening one profile.

The next architecture phase can convert those semantic operations into a
deterministic TaskGraph with explicit dependency, approval, and subagent
boundaries.


## Conversational task continuity

ActiveObjective is deliberately separate from generic memory. Agent starts,
blocked starts, and rejected starts persist a compact objective record. Ordinary
turns may carry that record forward as reference state until a newer objective
supersedes it or it reaches a terminal state.

A semantic parser may label the latest message with
`objective_relation=continue|resume|revise`. Only then may the bridge reuse the
previous **user-authored** canonical request. The LLM's paraphrase is never
treated as the new authority task. A profile mismatch between the compiled
latest request and the ActiveObjective prevents replay.

This makes turns such as "try again", "continue", "I attached the folder now",
and "same thing but..." robust without turning regexes into a second intent
classifier or replaying the unlimited transcript.
