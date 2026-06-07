# Phase 13.22 — live timing wrapper guard

## Context

A two-turn live/provider rerun after Phase 13.20 showed multi-minute stalls after the combined background LLM job finished and before the next turn became visible. The live timing artifact contained 5,000 `grounding_validation_ms` events from report/performance scan helpers rather than from the runtime grounding stage.

## Change

This slice narrows `live_manual_turn_timing` so wrapper selection excludes report/performance helper names such as scan, extract, collect, load, write, render, and append. It also excludes imported helper modules used by report generation and performance bridging.

## Verification target

The next operator rerun should first use a short smoke run. The expected evidence is no multi-minute gap between `combined_background_provider_call.end` and `campaign_state_commit.visible_to_next_turn`. RecursionError is not claimed fixed by this slice; it remains a separate runtime issue unless live evidence proves otherwise.
