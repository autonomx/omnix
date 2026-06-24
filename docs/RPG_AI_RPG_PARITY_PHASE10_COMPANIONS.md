# Phase 10 — Party and Companion System Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- Companion role and state contracts for fighter, healer, scout, merchant, guide, scholar, lockpick, and face roles.
- Loyalty, morale, fear, debt, personal goal, and active party tracking.
- Join eligibility helper using relationship, quest, conflict, loyalty, and fear inputs.
- Deterministic join and leave resolution helpers.
- Party role bonus helper for combat, healing, travel, social, knowledge, and lock checks.
- Report-friendly active companion payloads.
- Regression tests for eligibility, joining, leaving, clamping, party bonuses, and reports.

## Determinism Boundary

Companions join or leave only through deterministic eligibility and resolution helpers. LLM dialogue may explain the result, but it cannot add or remove party members directly.

## Verification

Pending GitHub Actions for this phase PR.
