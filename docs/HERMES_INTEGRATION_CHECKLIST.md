# Hermes Integration Checklist

This checklist summarizes the completed Omnix Hermes integration slices and the remaining production gates.

## Completed foundations

- Hermes can be installed by the main setup flow without interactive provider prompts.
- Omnix keeps Hermes disabled by default until the user configures and enables it.
- Settings shows disabled, offline, and reachable states with setup guidance.
- Settings provides a safe dry-run smoke test with compact result text.
- Agent Chat is opt-in; normal Chat remains the default path.
- Planning requests use a typed request and response shape.
- Planning context includes a small catalog of safe metadata names.
- Catalog readouts return payload rows without mutation.
- Review-first and observability notes are documented.

## Required runtime checks

A complete local validation pass should cover:

1. Hermes disabled: Settings shows disabled and no error.
2. Hermes enabled but sidecar offline: Settings shows offline and connection detail.
3. Hermes reachable: Settings shows reachable, health, and capability details.
4. Dry-run smoke test: result text shows dry-run state and does not change state.
5. Agent Chat off: messages use the normal provider path.
6. Agent Chat on: messages use Assist Core planning path.
7. Unknown catalog names: responses remain safe and non-mutating.
8. Review-required suggestions: user review is required before any future changing action.

## Production guardrails

- Do not run arbitrary shell commands from the browser.
- Do not enable mutable actions without explicit review UI.
- Keep dry-run paths non-mutating.
- Keep normal Chat behavior unchanged unless Agent Chat is enabled.
- Keep GitHub and file changes out of browser-side controls.

## Next production step

Add real API routes for `/api/hermes/status` and `/api/hermes/test` when the app router surface is ready, using the existing diagnostics helpers as the source of truth.
