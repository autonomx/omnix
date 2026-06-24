# Phase 15 — World Director and Long Campaign Pacing Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- Story arc contracts with status, pressure, beats, and threat.
- Director state tracking arcs, recent locations, NPCs, actions, danger, and downtime.
- Loop detection for repeated locations, NPCs, and actions.
- Pacing pressure updates.
- Grounded director suggestions from active arcs and valid actions.
- Arc advancement and report payload helpers.
- Regression tests for loop detection, pacing pressure, suggestions, pure arc advancement, and reports.

## Determinism Boundary

The director may suggest pacing and valid next actions. It does not mutate simulation state unless deterministic arc helpers are called.

## Verification

Pending GitHub Actions for this phase PR.
