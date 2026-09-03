# Agent Runtime Phases 15–19

## Status

Phases 15–19 extend Semantic Routing v2 with subject-correct evidence obligations and durable multi-profile execution.

Core rules:

**Acquisition may batch requirements; satisfaction may not infer coverage.**

**The TaskGraph is the authority envelope; the coordinator is not a super-agent.**

SemanticTask remains an untrusted description of meaning. Omnix continues to compile all executable authority deterministically.

## Phase 15 — Evidence Coverage Identity & Obligation Matching

Evidence requirements previously could collapse by source class. That is insufficient for React + Vue releases, GME + AMC filings, or any request with multiple subjects that share a source family.

EvidenceRequirement.id remains a persistence/tracing identifier. Semantic satisfaction is separate in EvidenceCoverage, which contains a coverage kind plus either a canonical SubjectRef or a deterministic coverage key.

Coverage resolution prefers:

1. canonical subject identity;
2. domain-specific deterministic identity such as software_package:react;
3. a stable semantic-dependency claim hash.

Raw fuzzy string matching is not an evidence trust boundary.

Requirements merge only when they represent the same canonical obligation:

    source class + coverage identity + purpose

Duplicate obligations merge monotonically: stronger trust wins, current freshness wins over timeless, fail-closed wins over fallback, stricter maximum age wins, minimum match counts do not decrease, and acceptable source alternatives cannot weaken trust.

All legacy evidence-merging paths use the same obligation merger.

EvidenceReceipt may declare multiple coverage identities. One acquisition can therefore retrieve React, Vue, and Svelte while the evaluator still verifies three independent obligations. A receipt never satisfies another subject merely because its capability or source class matches.

Receipt coverage is persisted in PostgreSQL and emitted in evidence events, so restart/recovery cannot erase subject coverage identity.

## Phase 16 — Deterministic Multi-profile TaskGraph

Semantic Routing v2 previously failed closed when a request required more than one profile. That boundary now compiles through TaskGraph.

Node kinds:

- evidence_read
- agent
- synthesis
- capability
- condition
- approval
- join

The semantic compiler emits profile-bound evidence/agent nodes plus authority-free
join/synthesis nodes. Capability, condition, and graph-level approval nodes are
runtime primitives reserved for explicitly constructed graphs; Phases 15–19 do
not claim that SemanticTask currently emits those three node kinds.

Edge kinds:

- data
- control
- condition
- approval

Each executable node independently owns its profile, objective, local/external capability ceiling, resource scopes, evidence policy, approval policy, success criteria, acceptance plan, model, limits, inputs, and outputs.

The coordinator owns none of those capabilities.

compile_task_graph partitions a validated SemanticTask by deterministic profile ownership. Every subtask still passes through compile_semantic_task and compile_task_authority. TaskGraph therefore does not create a second policy engine.

A node cannot request capabilities outside its profile. Workspace requirements are checked per node. Resolvable broker resources such as a ticker or explicit location are bound to ResourceScope. The compiler does not invent recipient/event IDs that were not semantically resolved.

unsupported_composite_profiles is the one former fail-closed compiler anomaly that may transition into start_task_graph. Other anomalies still fail closed, and ambiguity still requires clarification.

## Phase 17 — TaskGraph Scheduling, Parallelism & Aggregation

PostgresTaskGraphRuntime reuses the existing durable Agent runtime and governed capability bridge. The coordinator may atomically claim compiled nodes, launch already-compiled Agent envelopes, observe child status, pass declared outputs over graph edges, execute deterministic conditions, handle approval nodes, aggregate results, cancel work, and recover scheduling.

It cannot issue new node authority.

Independent ready Agent/evidence nodes run concurrently up to max_parallel_nodes. Dependency edges delay only consumers. An authority-free join performs fan-in.

Chat semantic reference context and predecessor outputs are supplied to a child Agent as reference-only context. They are not appended to the child's user-authored task and cannot change its issued capabilities.

Before execution, a node atomically transitions from pending to ready. Agent child run IDs are issued and persisted in that same claim before child launch. This prevents Chat polling, recovery, and supervision from double-launching one node.

Agent nodes are restart-safe because child identity is durable before launch. A claimed capability node whose external outcome is unknown after coordinator loss fails closed rather than executing twice.

A background supervisor periodically advances active graphs. Removed nodes remain auditable in revision/event history but are removed from the current execution set.

## Phase 18 — TaskGraph Steering, Recovery & Replanning

A TaskGraph is represented as an ActiveObjective with profile task-graph and its durable graph run ID.

Later semantic turns reuse TurnPlan relation semantics.

Continue adds work by reconstructing and reparsing the complete effective user-authored objective, then compiling a complete revised graph. This prevents latest-turn/reference-context semantics from being mistaken for an append-only execution order. Cross-profile operation order is preserved conservatively even when the parser does not label the request multi-step.

The durable revision planner diffs the complete previous and revised graph contracts. Unchanged completed/running nodes can be reused or retained, while a newly added dependency invalidates the affected downstream node so actions such as email/calendar delivery cannot race newly added evidence. Final synthesis remains authority-free.

Revise recompiles and replaces the current graph shape. Changed/removed running children are cancelled.

Replay reruns the graph without reusing completed outcomes. Opaque replay language such as "try that again" is resolved from the durable objective before graph compilation, so sparse replay semantics cannot fall through to Chat.

Safe reuse fingerprints the node's semantics, capability/resource authority, evidence policy, approval/limits, and incoming dependency contract.

An unchanged completed node can be reused. An unchanged running/waiting node can remain active. Changed nodes are invalidated. Authority reductions are tracked. Removed nodes cannot silently survive a revision.

## Phase 19 — Authority-preserving Optimization

Optimization runs only after authority compilation and cannot add capabilities, weaken evidence requirements, or alter approval policy.

Compatible evidence requirements may share an acquisition batch when capability, source class, trust, freshness, and fallback policy match. The batch still retains every requirement ID and coverage identity.

Topological levels identify parallel work.

Only explicitly cacheable read-only nodes receive cache keys. Mutation/action nodes are excluded from caching and speculative execution. Cache identity includes the full node fingerprint plus incoming dependencies.

Critical-path estimates provide deterministic cost-aware priority without changing graph dependencies.

Per-profile model overrides can choose a different model for execution. Model selection changes strategy only; node capability, resource, evidence, and approval authority stays unchanged.

## Persistence

Phase 15 migration:

    0057_agent_evidence_coverage.sql

TaskGraph migration:

    0058_agent_task_graph.sql

The durable graph schema stores graph runs, revision history, current node-run state, and ordered graph events. Graph events also flow through the existing PostgreSQL outbox.

## HTTP control surface

/api/task-graph-runs/{run_id} exposes durable status.

Additional controls expose ordered events, SSE event streaming, advance/recover, cancel, and approval/rejection.

Semantic graph revision remains a Chat/TurnPlan operation rather than accepting an arbitrary client-supplied authority graph.

## Safety invariants

1. LLM output never selects capabilities or profiles directly.
2. A graph coordinator never receives the union of node capabilities.
3. Every executable node is validated against its own profile ceiling.
4. Evidence satisfaction is coverage-bound, not source-class-bound.
5. Batched acquisition never implies batched satisfaction.
6. Graph data edges are reference data, not execution authority.
7. Ambiguous/non-composite compiler anomalies still fail closed.
8. Mutation nodes are neither cached nor speculatively executed.
9. Unknown capability outcomes after coordinator loss are not retried.
10. Steering may reduce or remove authority but never silently retain it.

## Test responsibilities

Phase 15 tests cover same-source/different-subject obligations, explicit multi-coverage receipts, and monotonic merging.

Phase 16 tests cover per-node profile/capability/resource separation and workspace requirements.

Phase 17 tests cover dependency readiness and the reference-data/authority boundary.

Phase 18 tests cover completed/running reuse, invalidation, authority reduction, removed/added nodes, and context-dependent continuation edges.

Phase 19 tests cover evidence batching, mutation cache exclusions, parallel levels, critical-path priority, and authority-neutral model selection.

TurnPlan tests pin the production composite and active-graph steering boundaries.


## Live LLM validation matrix

The deterministic unit/integration suites are complemented by an opt-in live
GPT-5.6 Luna + high reasoning matrix:

    src/tests/agent_runtime/test_live_taskgraph_phases_15_19.py

The live suite covers conversation depths 1 through 10 and exercises:

- Phase 15 same-source/different-subject evidence coverage;
- current versus historical as-of evidence identity;
- Phase 16 multi-profile graph compilation and fail-closed interleaving;
- single-turn producer-to-action dependencies such as quote -> email;
- coding acceptance parity inside composite graphs;
- trading/research authority separation;
- Phase 17 continuation dataflow and authority-free synthesis;
- bounded Chat reference context passed to graph children;
- Phase 18 Agent <-> TaskGraph supersession, replay, narrowing, cancellation,
  and non-resurrection;
- live Chat-bridge graph/Agent replacement using recording durable services;
- Phase 19 batching/cache/speculation/model-plan invariants without executing
  real external tools.

Run the full matrix from PowerShell:

    .\scripts\run_live_taskgraph_phase_tests.ps1

Run one scenario:

    .\scripts\run_live_taskgraph_phase_tests.ps1 -Scenario depth_06_executor_supersession

Fast mode is available for iteration:

    .\scripts\run_live_taskgraph_phase_tests.ps1 -FastMode

The suite is deliberately opt-in because it requires an authenticated Codex
app-server and makes live model calls. It does not execute real home, email,
calendar, market, web, or workspace tools. Live model output supplies semantic
meaning only; all authority assertions remain deterministic Omnix checks.
