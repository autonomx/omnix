# ADR 0015: No runtime patching; explicit extension points

Status: accepted.

Runtime composition must not change imported classes, foreign module attributes,
standard-library functions, import finders or module caches. Such changes make
behavior depend on import order, conceal authority boundaries and prevent
independent feature lifecycles. Composition owns wiring, and each owning module
owns its implementation.

Use constructor parameters, typed service containers, registries with explicit
registration and lifecycle hooks, or an ordinary change to the owning class.
Feature contracts must name their dependencies. Registries do not grant agent,
worker or trading execution authority; the existing deterministic authority and
durable ownership checks continue to apply.

`python scripts/architecture_lint.py --check` enforces the architecture rules in
the enterprise roadmap. Existing violations are recorded by rule, path and stable
fingerprint in `resources/architecture/lint-baseline.json`. New violations are
rejected. Duplicate occurrences are counted, so copying an existing patch is a
new violation. Fixed entries must be removed with `--update-baseline`, which can
only shrink the baseline. Lines are diagnostics and never identities. Changes to
the rules or layer configuration require an explicit policy migration, rather
than an automatic baseline update.

Migration edits, deletion, new duplicate prefixes and out-of-order additions are
not eligible for baseline exceptions. Base-branch content and the committed
checksum registry protect historical migrations without renumbering them.
Registry maintenance must preserve existing checksums and append newly accepted
migrations. Migration lint runs on source and never connects to a database.

Tests may use scoped fixture replacements with automatic restoration. Production
code must expose the required injection seam rather than a test-only installer.
Browser patch enforcement is supplied by the ESLint work package. Static Python
lint is a guardrail, not a replacement for runtime capability enforcement,
characterization tests, or the roadmap's removal of existing patches.
