# ADR 0010: PostgreSQL production authority

Status: accepted.

Production structured state uses PostgreSQL exclusively. Files remain blob/artifact storage; explicitly authorized legacy import/test processes may use old representations. Availability failures must not create competing authority through SQLite, JSON or memory fallback.

Production bootstrap validates schema and authority before feature composition. Readiness probes do not apply migrations. Transaction-scoped repositories enforce tenant context, idempotency and atomic writes. Static/import and real PostgreSQL gates cover the boundary. This sacrifices offline production mutation in exchange for reliable recovery and one authoritative history.
