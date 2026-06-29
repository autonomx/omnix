# Hermes Test Message Notes

Phase 12 records the desired Settings behavior after the API module is present.

## Desired behavior

- The Settings test button should call the Hermes API module directly.
- If the call is unavailable, the card should show a clear message.
- The card should not create a separate chat session as a hidden fallback.

## Acceptance

- Successful test: show the returned result text.
- Unavailable test: show a visible message.
- Normal Chat remains unchanged.
- Agent Chat remains opt-in.
