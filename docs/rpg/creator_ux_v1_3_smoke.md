# Creator UX v1.3 smoke checklist

Targeted regeneration for factions, locations, NPCs, opening, and tensions.

## Prerequisites
- Backend: `POST /api/rpg/adventure/regenerate` endpoint is live.
- Frontend: Adventure Builder has regeneration buttons in Step 3 and Step 5.

## Factions
- [ ] Open Step 3 with an empty faction list → click "Regenerate Factions"
- [ ] Verify faction list is populated
- [ ] Manually edit a faction → click "Regenerate Factions" again → verify manual edits are replaced
- [ ] Confirm locations and NPCs remain intact after regenerating factions

## Locations
- [ ] Open Step 3 with an empty location list → click "Regenerate Locations"
- [ ] Verify location list is populated
- [ ] Click "Regenerate Locations" again → verify new locations generated
- [ ] Confirm factions and NPCs remain intact

## NPCs
- [ ] Open Step 3 with an empty NPC list → click "Regenerate NPCs"
- [ ] Verify NPC list is populated
- [ ] Click "Regenerate NPCs" again → verify new NPCs generated
- [ ] Confirm faction/location references in NPCs still render correctly

## Opening
- [ ] Go to Step 5 → click "Regenerate Opening"
- [ ] Confirm preview updates with new opening situation
- [ ] Verify starting location and starting NPCs update when resolved

## Tensions
- [ ] Go to Step 5 → click "Regenerate Tensions"
- [ ] Confirm review step shows updated preview metadata

## Durability
- [ ] Save draft after regeneration
- [ ] Refresh the page
- [ ] Confirm regenerated sections persist in draft

## Button behavior
- [ ] During regeneration, button text changes to "Regenerating…" and is disabled
- [ ] After regeneration completes, button text returns to normal label
- [ ] Other sections are not affected during regeneration