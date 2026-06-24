# Phase 14 — Modding, Lorebook, and World Packs Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- Lore entry contracts with scope, priority, and visibility.
- World pack contracts for regions, locations, factions, NPC templates, item catalogs, encounters, quest seeds, lore, and overlays.
- Mod overlay contracts for items, services, NPCs, factions, quest hooks, prompt style, and visual style.
- Validation for lore entries, overlays, and world packs.
- Guardrails that block overlay keys from directly mutating player state, currency, XP, combat HP, or quest status.
- Visible lore selection by scope and priority.
- Report-friendly world pack payloads.
- Regression tests for validation, lore sorting, forbidden keys, pure overlay updates, and reports.

## Determinism Boundary

World packs can seed content and style. They cannot directly mutate simulation state or bypass deterministic resolvers.

## Verification

Pending GitHub Actions for this phase PR.
