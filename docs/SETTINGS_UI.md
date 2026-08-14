# Settings UI

Phase 19 note.

The Settings card should use the browser helper from `src/apps/web/src/api/hermesClient.ts` for the test action.

Expected behavior:

1. The button calls the helper surface.
2. If the route is unavailable, the card shows a visible message.
3. The card must not create a separate chat session as a hidden alternate path.
4. Normal Chat remains unchanged.
5. Agent Chat remains opt-in.
