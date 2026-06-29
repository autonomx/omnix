# Hermes Review Notes

This note records the review-first rule for future Hermes additions.

## Review-first rule

Omnix should show suggested changes to the user before anything changes.

## Current safe baseline

- Normal Chat stays default.
- Agent Chat stays opt-in.
- Diagnostics are dry-run only.
- Settings shows setup commands as copyable text, not browser-run commands.

## Next UI shape

A future Settings card can show a suggestion with:

- a title;
- a short summary;
- the affected area;
- a clear confirmation state;
- a cancel path.

## Acceptance

The first suggestion card should be informational. It should not alter files, settings, repository data, or shell state.
