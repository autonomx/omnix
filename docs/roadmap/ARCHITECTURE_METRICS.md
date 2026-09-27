# Architecture scorecard and ratchet

`scripts/architecture_metrics.py` uses Python's standard library and never
imports the application. It emits all 49 Appendix E metrics, their direction,
and their certification targets. `--check` fails if any metric worsens against
`resources/architecture/metrics-baseline.json`. `--update-baseline` writes only
an equal or better complete measurement. Unknown values, syntax errors, metric
contract changes, and invalid evidence fail the check. Certification targets
are separate from this incremental ratchet.

Run from the repository root:

```powershell
python scripts/architecture_metrics.py --output artifacts/architecture-metrics.json
python scripts/architecture_metrics.py --check --output artifacts/architecture-metrics.json
python scripts/architecture_metrics.py --update-baseline --output artifacts/architecture-metrics.json
```

`--output` cannot name the baseline. Updates use an atomic replacement after
comparison. Reports retain evidence, including cycles, state candidates,
unreachable modules, API paths missing from OpenAPI, and both mypy override
patterns and their actual matching modules. The Appendix E mypy metric counts
override patterns; expanded matches support the kernel and percentage budget.
A new or deleted source file must be reflected in Git's
index before it can be represented by the tracked-file scan. Untracked operator
data is never discovered through a recursive workspace walk.

## Measurement scope

Input comes from `git ls-files`, with tracked deletions respected. Vendor trees,
virtual environments, `node_modules`, `.tools`, and generated web API contracts
are excluded from source counts. The generated OpenAPI document is read
separately as the authoritative endpoint and schema catalog. Symlinks and paths
escaping the repository are rejected. `--revision` reads a committed source
revision; dynamic evidence must match the sources being measured.

Python production rules cover `src/app` and the model servers, launchers, and
Python startup hooks listed in `resources/architecture/layers.toml`. The
explicit `src/app` scopes for AL008, AL010, the foreign-assignment score, and
direct requests are preserved. Startup-hook assignments remain lint evidence.
Operator scripts can print CLI results. Size metrics include tracked Python and
TypeScript tests and scripts. The fixed-sleep metric counts literal `time.sleep`
calls, as Appendix E specifies. Literal `asyncio.sleep` and Playwright
`wait_for_timeout` calls are retained separately as triage evidence.

Foreign writes use shared lexical binding and class provenance for AL003 and
the scorecard. Imported objects, module registries, typed class parameters,
aliases, closures and branch alternatives are tracked without executing code.
Locally owned classes and instances remain distinct from imported classes;
parameter and comprehension bindings shadow outer imports. Aliased built-in
setters and implicit assignment targets are checked. This is syntactic analysis,
not whole-program execution: unresolved class-shaped parameters remain
conservative candidates, and dynamic behavior needs characterization coverage.

The initial detector audit corrected the provisional inventory by measuring the
preserved original source snapshot with the corrected checker. The original
source digest matches its captured runtime evidence. Before the subsequent STT
error-path fix, all 2,781 production inputs were verified unchanged and the
current lint inventory matched the corrected original inventory. The app-only
foreign-write count changes from 496 to 499 and install-hook functions from 135
to 136. These are corrected measurements of existing code. The archived audit
records the original and corrected reports; the CLI ratchets remain strict.

Layer checks allow imports within the same feature. Imports of another feature's
implementation remain violations; registered public contracts are introduced by
WP-2.2. The current cycle count measures two-way package import relationships,
matching the review's initial cycle measure. Lazy imports are layer checked but
do not create module-level cycles.

An unbounded persistence `fetchall` is a call whose query cannot be proven to
contain a SQL `LIMIT` in its own scope. This includes unknown queries. Global
mutable containers and locks are state-inventory candidates; explicit inventory
entries also count, including singletons initialized to `None`. Approval requires
an exact path, symbol, and nonempty reason. This initial report is a syntactic
inventory with explicit approval flags, augmented by manual entries from
`process-local-state.json`. WP-6.6 completes the semantic inventory.

Web detectors use comment-aware lexical analysis for established source forms.
API coverage includes distinct literal paths and unresolved calls outside the API
package. Route factories count concrete invocations. Generated schema aliases
are excluded from handwritten API type counts. Reachability follows literal
imports, dynamic imports, and relative `import.meta.glob` patterns. Unreachable
results are candidates for Appendix F review, not permission to delete code.

## Dynamic evidence

Five metrics need a fresh runtime report: collection errors, boot imports, RLS,
retention execution, and outbox consumer coverage. Missing values are unknown.
Reports must match the source digest, name the disposable environment, and be
less than 48 hours old. Regenerate them for each source change and CI run:

```powershell
# Set this to an explicitly provisioned, task-owned loopback test database.
$env:OMNIX_TEST_DATABASE_URL = 'postgresql://omnix_test:architecture-test-only@127.0.0.1:5432/omnix_test'
python scripts/architecture_runtime_metrics.py --output artifacts/architecture-runtime.json
python scripts/architecture_metrics.py --check --runtime-report artifacts/architecture-runtime.json --output artifacts/architecture-metrics.json
```

The producer copies tracked inputs to its own temporary source snapshot. Fresh
isolated Python processes perform boot, read-only database measurement, and full
tracked-test collection. ASGI lifespan workers are not started. Audit guards deny
provider socket connections, subprocesses, and writes outside that temporary
directory. Database URLs require an explicit loopback host, port, user, and
disposable database name; query overrides and inherited libpq settings are
rejected or removed. Application startup may initialize only this disposable DB.

Boot measures newly imported Python modules during actual production assembly.
Collection preserves the selected pytest configuration and records its import
mode and strict-marker setting. Probe-boundary collection failures remain errors
and are identified in the evidence. A pytest internal failure or incomplete
probe cannot certify a baseline.

RLS includes tables with a workspace key and their transitive foreign-key child
tables. Retention coverage counts enabled policies represented in completed
cleanup runs from the past 48 hours, including the current repository's shortened
report keys. With no registered outbox consumers, verified initial coverage is
zero. The first consumer registration forces replacement with a registry-backed
runtime measurement; it cannot silently retain that initial zero.

The initial local evidence uses Windows and Python 3.11.12. The temporary CI
profile uses Ubuntu and the roadmap's supported Python 3.11 with explicit direct dependency pins. WP-1.3
must establish hashed locks and a canonical measurement profile before CI/runtime
comparability and WP-1.1 acceptance can be declared complete. Archived evidence
documents a measurement; CI always produces fresh evidence.
