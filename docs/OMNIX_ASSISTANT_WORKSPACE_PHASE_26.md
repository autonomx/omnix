# Phase 26 — Settings and Preferences

Phase 26 introduces durable assistant workspace preference contracts.

## Scope

- Define stable appearance and density settings.
- Preserve accessibility preferences such as reduced motion.
- Preserve live voice caption defaults.
- Keep preference derivation as pure helpers so UI projections can consume them safely.

## Acceptance

- Preferences have deterministic defaults.
- User overrides merge without mutating defaults.
- UI behavior helpers are pure and covered by tests.
