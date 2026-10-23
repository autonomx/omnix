# RQ-5.7 Rewind and save points: undo a mistake, return to a moment

## What the player experiences

"Undo last turn" restores the game as it was before the last turn. Named save points ("Before the gate") can be made
at any time and returned to later. Both are unavailable in hardcore campaigns.

## Rules

- Rewind and restore are `structured_action` turns (roadmap §4.1). They write a **new** revision whose document is
  an earlier revision's document (rebuilt from the nearest snapshot plus patches, then verified against that
  revision's `state_hash_after`); history is never rewritten.
- Undo goes back one player turn (skipping world-tick and system turns in between).
- Save points: up to 20 per campaign, stored as pinned snapshots (migration 0170) with a name; restoring one is a
  rewind to its revision. Deleting a save point unpins it.
- Narration of the undone turns stays in history, marked superseded; the journal shows "Returned to …".
- The world clock rewinds with the document (it lives in it), so the world is exactly as it was.

## State it changes

`RevisionRestored` (carries the source revision), `SavePointCreated`, `SavePointDeleted`.

## Scenarios

Buy something, undo, the purse and inventory are as before; make a save point, play five turns, restore it; undo
refused in hardcore.

## Out of scope

Branching timelines shown as a tree, sharing save points between campaigns.
