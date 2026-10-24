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

## As built (RQ-5.7)

`POST /api/rpg/sessions/{id}/rewind` (no body: undo; `{"save_point": name}`: return to it) is a structured-action turn
(`session/turn/run.py` `_rewind_turn`): the target is the revision before the hero's last turn, walking back past world
ticks, upgrades and earlier rewinds (`session/turn/rewind.py` `undo_target`), or the save point's; the repository
rebuilds that revision's document from the nearest snapshot and the turns' patches, checking every hash
(`document_at_revision`); `RevisionRestored` puts back the sheet, the simulation, the game's runtime sections and the
turn count, while the campaign's bookkeeping (revision, interactions, narrations) goes on. Each turn row's command
records its kind (`turn_kind`, and `restored_revision` for a rewind). Every revision written outside a turn (the
campaign's first, an edit) now keeps its document as a snapshot, so the history can rebuild every revision. Save
points: `POST/GET /save-points`, `DELETE /save-points/{name}` (migration 0183 `save_point_name`; at most 20; none in
hardcore). Not yet: the undone turns' narration marked superseded, the play screen's buttons (RQ-7).

## Out of scope

Branching timelines shown as a tree, sharing save points between campaigns.
