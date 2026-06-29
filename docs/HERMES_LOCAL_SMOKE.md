# Hermes Local Smoke Checklist

Run this locally after pulling the latest `rpg` branch.

## Server state checks

1. Start the gateway normally.
2. Open Settings.
3. Confirm the Hermes status card renders.
4. With Hermes disabled, confirm the card shows a disabled state and setup guidance.
5. Enable Hermes env values but leave the sidecar stopped; confirm the card shows an offline state.
6. Start the sidecar; confirm the card shows a reachable state.

## Action checks

1. Click Refresh and confirm Settings reloads without changing chat state.
2. Click the dry-run test button and confirm a visible status message appears.
3. Confirm no hidden chat session is created by the test button.
4. Open Normal Chat and confirm normal chat still works unchanged.
5. Open Agent Chat and confirm agent behavior remains opt-in.

## Follow-up

If typed Hermes routes are desired in generated OpenAPI, regenerate and commit the generated OpenAPI and TypeScript files in a dedicated slice.
