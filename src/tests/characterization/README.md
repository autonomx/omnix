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

## Published-world scenario

`rpg-published-world` (RQ-0.2) imports Aurelia from its bundle, adopts it,
launches its "Gateborn: First Light" opening and plays 30 turns through the
turn route, plus one tactical grid move: look, talk, ask a price, buy, sell,
drop, leave and return, pick up, a meal, a room and a night's sleep, wait,
a fight with a move on the grid, fleeing, a quest taken and advanced, and
travel there and back. The scripted model is
`tests.rpg.playthrough.scripted_model.ScriptedRoleModel`: it classifies each
call by the registered prompt template it was rendered from and answers by
semantic role (intent, dialogue, narration, lore, ...), so changing a call's
wording or answer shape changes the adapter, not the recording.

The golden records, per step: the response's changed domains and source, what
the turn changed (fact by fact: place, people present, purse, pack, health,
quests, party, needs, skills, the fight) and the document sections its state
patch touched, the session summary, the facts after the turn, the roles of
the model calls made, and a hash of the normalized campaign document (ids,
times and the world's content hashes as placeholders; the stored stage
timings and the creator preview id left out, as they are not reproducible).
Its prose is in `rpg-published-world-prose.json`, which may be re-recorded
without justification when only wording changed (`OMNIX_UPDATE_PROSE=1`).

## Trading evaluation scenario

`trading-evaluate` replays a fixed, reviewed market-bar fixture through the
strategy monitor. It records the entry proposal, paper authorization decision,
submitted paper order, fill, protection state, and strategy events. The golden
was captured before folding the import-time trading overlays into their owners.
