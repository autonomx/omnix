# Characterization tests

These scenarios freeze externally observable behavior immediately before a
refactor. They capture values at a public route or pipeline boundary, normalize
only nondeterministic identifiers and time data, and compare the result with a
reviewed JSON golden.

Run the characterization suite with:

```text
python -m pytest src/tests/characterization -q --tb=short
```

To introduce a scenario, add its test and golden in the same PR **before**
changing the behavior it records. Set `OMNIX_UPDATE_GOLDEN=1` only for that
scenario-introduction run, review the generated JSON, then unset it. State in
the PR description that the golden captures the pre-refactor behavior. Once a
scenario is merged, a golden change requires a separate behavior-change PR and
written justification.

The shared fakes in `fakes.py` do not start providers or connect to live
services. `FakeLLMProvider` selects scripted responses using a SHA-256 digest
of canonical prompt messages; `FakeTTS` returns fixed bytes; `FakeMarketData`
returns an explicitly supplied bar series. Add deterministic inputs alongside
each new golden.

`harness.capture(name, fn)` requires a dictionary result and a checked-in golden.
The harness replaces timestamps, durations, and UUIDs in first-seen order,
rounds floats to six decimals, preserves ordered sequences, and sorts sets.

## Live voice scenarios

`live-voice-prompt` fixes a character identity, conversation profile, approved
memory record, recent transcript and current spoken user turn. Its golden records
the assembled provider messages and prompt-budget diagnostics.

`live-voice-tts-lane` fixes streamed response text, records the existing phrase
splitter's complete phrases and final tail, and schedules deterministic PCM
frames through the accepted TTS lane using `FakeTTS`.

## RPG turn scenario

`rpg-production-turn` plays a seeded new game (seed 7) through the production
turn route, `POST /api/rpg/sessions/{id}/turn`, against PostgreSQL: look, talk,
buy, travel and wait. Model calls are answered by a scripted fake keyed on each
call's contract (semantic intent, narration candidates, turn narration, canon
dossier) and the narrative engine writes through a scripted structured writer.
The golden records each turn's visible response, interaction and simulation
counters, changed domains, state revision, session summary, narrative blocks
and validation, and the kinds of model call the turn made. It replaced the
earlier `rpg-turn` golden, which exercised an execution pipeline production
never used (2026-10-04).

## Trading evaluation scenario

`trading-evaluate` replays a fixed, reviewed market-bar fixture through the
strategy monitor. It records the entry proposal, paper authorization decision,
submitted paper order, fill, protection state, and strategy events. The golden
was captured before folding the import-time trading overlays into their owners.
