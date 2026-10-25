# RQ-6.2 / RQ-6.3: the turn stream, outcome first

The play screen follows each turn on a stream (roadmap §4.7). The outcome card shows when the turn commits; the
narration streams in after it.

## The request

- The client sends `X-Omnix-Rpg-Turn-Stream: 1` with the turn and opens
  `GET /api/rpg/sessions/{session_id}/submissions/{submission_id}/stream` when the answer says the narration is
  pending.
- A turn the narrative writer must narrate commits with no narration (the commit stage skips the writer:
  `session/turn/narration_timing.py`). The answer comes at the commit: the TurnOutcome, the outcome card's facts, and
  `narration: {status: "pending", stream_path}`.
- The writer then narrates beside the request (`turn_pipeline._narrate_after_commit`). Its drafts reach the stream,
  and the response is inserted into `omnix_rpg_narrative_responses` and its delivery opened. The campaign is not
  saved: the narration's session writes are staged and dropped, as inside a turn.
- A turn whose words are already written (the game's own lines, a person's line) commits them with the turn, as
  before, and its stream ends at once.
- A turn submitted without the header (Hermes, jobs, tools, tests) narrates inside its commit, as before.

## The stream

`foundation/turn_stream.py` keeps each submission's events in order, in this process, for ten minutes. A reconnect
with `Last-Event-ID` (or `?after=`) resumes.

| Event | Data |
|---|---|
| `accepted` | the submission id |
| `committed` | turn and interaction ids, the revision |
| `outcome` | the TurnOutcome |
| `narration.delta` | the text written so far |
| `narration.final` | the visible response, the narrative response id |
| `error` | the stage and a message; the turn still stands when narration fails |

A stream that no process holds (another replica, expired) answers `error: turn_stream_not_found`. The campaign
still holds what happened: reading it fills each recent turn's narration from the response table
(`narration_timing.with_narrations`).

## Open

- A crash between the commit and the narration's insert leaves the turn without the writer's prose. Its interaction
  row was committed with the turn's own lines (what the rules did), so reading the campaign shows those. A durable
  job that narrates such a turn later is optional.
- The map surface still polls; it moves onto the stream with RQ-7.1.
- Hermes waits for `narration.final` instead of narrating inline (RQ-1.6 note).
- One process holds a stream. Several gateway replicas need the PostgreSQL event log for it, as the narration
  events have.
