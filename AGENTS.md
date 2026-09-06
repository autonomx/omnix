# Omnix Engineering Guidance

Omnix is a mixed Python + React/TypeScript repository with durable agent, trading, persistence, speech, and web subsystems. Treat this file as repository engineering guidance; Omnix runtime policy and issued capabilities remain authoritative.

## Engineering workflow

For implementation work:

1. Inspect the relevant module, callers, tests, registrations, schemas, migrations, and generated contracts before editing.
2. Identify which layer owns the behavior and preserve its invariants.
3. Make the smallest coherent change that satisfies the request; avoid downstream patchwork when the root contract is wrong.
4. Add or update focused regression coverage for changed behavior.
5. Inspect the complete final diff and search impacted call sites before declaring the implementation ready.
6. Run task-relevant validation after the final code change. Earlier passing tests are stale after a mutation.

## Python

Prefer the repository's existing pytest configuration and focused test files before broad suites.

Typical checks include:

- `python -m pytest <focused-test> -q --tb=short`
- `ruff check <changed-python-paths>` when lint is relevant/configured
- project-specific type checks where an existing configuration exists

Do not install new developer tools merely to satisfy a generic checklist unless the task explicitly requires that dependency.

## React / TypeScript web app

The main web package is under `src/apps/web`.

From repository root, prefer package-scoped commands such as:

- `npm --prefix src/apps/web run test -- <focused-test>`
- `npm --prefix src/apps/web run build`
- the package's existing typecheck command when applicable

Keep UI behavior, CSS ownership, component tests, and generated API contracts in sync.

## Agent runtime / authority-sensitive code

For `src/app/agent_runtime`, capability authority, approvals, evidence, acceptance, TaskGraph, persistence, and recovery are security/correctness boundaries.

- Profiles are ceilings, not grants.
- Approval policy must never expand issued capabilities.
- Coordinator/reviewer/subagent authority must remain explicitly narrowed.
- Durable PostgreSQL state is authoritative for recovery-sensitive lifecycle decisions.
- Evidence and validation must be bound to the correct subject/task revision/workspace state.
- LLM output is evidence or a proposal; deterministic Omnix code owns authority and completion.

## Persistence

Schema changes require a forward migration under `src/app/persistence/migrations` plus relevant persistence tests. Preserve idempotency and recovery semantics.

## Trading

AI trading/shadow analysis is research unless a deterministic strategy/runtime explicitly owns execution authority. Do not widen order/trading authority as a side effect of research or agent changes.

## Shell/runtime constraints

Agent shell commands are intentionally narrow. Avoid shell composition (`;`, pipes, redirection, command substitution) and issue commands separately. Stay inside the issued workspace and use repository-root commands rather than changing shell directories when package-prefix options exist.
