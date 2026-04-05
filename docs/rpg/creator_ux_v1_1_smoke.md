# Creator UX v1.1 smoke checklist

Manual verification checklist for the Creator UX v1.1 hardening pass.
Run these tests after any code changes to the creator / adventure-builder flow.

## Launch

- [ ] Create from blank setup
      - Open Adventure Builder with empty/new adventure
      - Fill minimal required fields (title, genre, setting, premise)
      - Launch and confirm adventure starts successfully

- [ ] Create from template
      - Pick a template (e.g. "Fantasy Adventure")
      - Verify all template fields are populated
      - Launch and confirm adventure starts successfully

- [ ] Edit premise after template hydration
      - Load a template
      - Edit the premise text
      - Launch and verify customised premise appears in opening narration

- [ ] Launch with validation warnings
      - Create an adventure with warnings (e.g. no locations, no NPCs)
      - Confirm warnings are displayed but launch button is enabled
      - Launch successfully

## Runtime integration

- [ ] Play 5 turns after launch
      - Enter text input 5 times
      - Verify narration appears each time
      - No errors in browser console

- [ ] Verify NPC panel renders
      - After launch, NPC panel should show any starting NPCs
      - NPC cards should display name, mood, and action buttons

- [ ] Verify world/player state renders
      - World info (title, genre) should be displayed
      - Player panel should show stats (open via stats button)
      - Player HP / stamina / mana bars visible

- [ ] Verify no JS errors in console
      - Open browser DevTools console
      - Perform all actions above
      - Confirm no red errors appear

## Session durability

- [ ] Refresh after launch
      - Launch an adventure
      - Refresh the browser page
      - Verify session persists (no blank flash)
      - Verify messages are still visible

- [ ] Resume active session
      - After refresh, enter text to continue the adventure
      - Confirm turn executes successfully

- [ ] Start a second new adventure
      - Click "New Adventure" button
      - Confirm Adventure Builder opens
      - Create and launch a second adventure
      - Verify previous session is cleared

- [ ] Save/reload if save flow exists
      - Save current session (if save functionality exists)
      - Reload page
      - Load saved session
      - Verify session restores correctly

## Validation / preview

- [ ] Confirm blocking issue disables launch
      - Create an adventure with blocking validation issues (e.g. missing title)
      - Verify launch button is disabled or error is shown
      - Confirm validation errors are displayed

- [ ] Confirm warning does not disable launch
      - Create an adventure with warnings only (no blocking issues)
      - Verify launch button remains enabled
      - Launch successfully

- [ ] Confirm preview location/NPC names update after edits
      - Create a setup with location and NPC
      - Edit location name or NPC name
      - Open preview and verify changes reflected
      - Launch and verify changes in game

## Legacy redirect

- [ ] Trigger old New Adventure entry points
      - If any UI elements previously triggered the old `create-game` endpoint, test them
      - Confirm they route into Adventure Builder instead

- [ ] Check deprecation headers
      - Use browser DevTools Network tab
      - Trigger legacy game creation endpoint
      - Verify response headers include:
        - `X-Omnix-RPG-Legacy-Create: true`
        - `X-Omnix-RPG-Recommended-Create: /api/rpg/adventure/start`

- [ ] Check console warning for legacy calls
      - Open browser DevTools console
      - Trigger any legacy showSetupModal() call
      - Confirm warning message logged: `[RPG] Legacy showSetupModal() invoked; redirecting to Adventure Builder`

## Regression smoke

- [ ] Run unit test suite
      ```
      pytest src/tests/unit/rpg/test_phase90_creator_ux_v1.py -v
      ```
      Confirm all tests pass.

- [ ] Verify response version constants
      - Preview response should include `response_version: 1`
      - Start response should include `response_version: 1` and `start_response_version: 1`

- [ ] Test partial/broken payload handling
      - Use curl or a tool to send malformed setup data to preview/start endpoints
      - Confirm graceful handling (no 500 errors)

## Notes

- This smoke checklist is intended for manual verification; many checks may be
  automated over time.
- If any check fails, file a bug and note the workaround before merging.