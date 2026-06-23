# Phase 27 — Responsive Layout and Accessibility

Phase 27 adds deterministic contracts for responsive workspace layout and baseline accessibility behavior.

## Scope

- Define responsive breakpoint names used by assistant workspace projections.
- Derive predictable panel counts for mobile, tablet, and desktop layouts.
- Capture keyboard, screen-reader, reduced-motion, and high-contrast affordance flags.
- Keep accessibility derivations pure so UI components can consume them safely.

## Acceptance

- Breakpoints map to deterministic layout capacity.
- Accessibility readiness is derived from keyboard and screen-reader support.
- Motion behavior respects reduced-motion settings.
