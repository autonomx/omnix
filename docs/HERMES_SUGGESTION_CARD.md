# Hermes Suggestion Card

Phase 13 defines the review-first suggestion card contract for Hermes Settings.

## Card fields

- Title
- Summary
- Affected area
- Review state
- Confirm label
- Cancel label

## Initial behavior

The first card is informational only. It should explain the next setup step and ask the user to review it. It should not change files, settings, repository state, browser state, or shell state.

## Default copy

Title: Review Hermes setup suggestion

Summary: Hermes can suggest setup steps, but Omnix will show them for review before anything changes.

Affected area: Settings

Review state: review required

Confirm label: Reviewed

Cancel label: Dismiss

## Guardrails

- No automatic changes.
- No browser-run shell commands.
- No hidden chat-session fallback.
- Normal Chat stays unchanged.
- Agent Chat stays opt-in.
