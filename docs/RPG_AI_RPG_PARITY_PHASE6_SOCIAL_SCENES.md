# Phase 6 — Conversation and Social Scene Upgrade Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- `SocialThread` for directed, ambient, group, argument, negotiation, interrogation, and party-banter scenes.
- `SocialSpeakRequest` and `SocialSpeakDecision` for deterministic NPC speaking gates.
- Gate reasons for inactive threads, thread mismatch, NPC absence, player leaving, repeated speaker blocking, direct address, urgent reaction, relationship trigger, ambient budget exhaustion, and regular scene participation.
- `apply_speak_decision` to update last speaker and ambient budget only when speaking is allowed.
- `SocialMemoryHook` and `build_memory_hook` for resolved-event-driven memories such as promises, threats, secrets, deals, insults, and clues.
- Report-friendly social scene payloads.
- Regression tests for direct speech, ambient budget blocking, repeated speaker blocking, budget updates, memory hooks, and report payloads.

## Determinism Boundary

The social scene helpers decide whether an NPC is allowed to speak and whether a memory hook exists from already-resolved events. LLM dialogue may render allowed speech, but it cannot create extra turns, bypass ambient budgets, or write memory without a deterministic hook.

## Verification

Pending GitHub Actions for this phase PR.
