# Phase 13.47 — skip redundant combined background LLM jobs

## Context

A slow successful turn showed foreground runtime/manual narration calling the LLM, followed immediately by a combined background LLM submission. That creates double LLM pressure: one blocking foreground provider call and one background provider call competing for the same local provider.

## Change

This slice adds a loader-level wrapper around generated combined-background submit functions. Default behavior is `auto`:

- skip the combined background submit when the submitted argument tree already contains `llm_called=True`
- preserve submission when no foreground LLM call is visible

Environment control:

- `RPG_AUTOPLAY_SKIP_COMBINED_BACKGROUND_LLM=0` disables the guard
- `RPG_AUTOPLAY_SKIP_COMBINED_BACKGROUND_LLM=1` skips all combined background submissions
- unset / `auto` skips only redundant submissions

## Expected effect

This should reduce local provider contention after foreground runtime narration without changing deterministic simulation state. It does not yet remove the foreground runtime LLM call itself; that remains the larger follow-up optimization.
