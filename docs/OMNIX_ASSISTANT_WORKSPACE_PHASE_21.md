# Omnix Assistant Workspace Phase 21 — Browser Audio Capture

Phase 21 adds pure audio capture state contracts.

## Scope

- Track permission state, available devices, selected device, and active capture state.
- Select capture devices immutably.
- Derive whether capture can start.

## Acceptance criteria

- Capture requires granted permission and a selected device.
- Device records are copied into state.
- Helpers stay independent from browser APIs.
