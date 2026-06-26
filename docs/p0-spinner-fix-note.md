# RPG P0 spinner performance fix

This slice addresses a foreground latency regression where safe NPC dialogue could still wait on `rpg.turn` job completion and duplicate local LLM calls.

## Fixes

- Optional RPG runtime hooks now install independently, so one older optional hook cannot prevent the P0 fast visible-dialogue hook or visible-response guard from installing.
- Active duplicate `rpg.turn` jobs for the same session and command reuse the existing job instead of launching another background turn.
- RPG turn visible response formatting collapses repeated speaker lines such as `Bran: text` followed by `Bran: "text"`.

## Scope

Stateful commands still use the normal runtime path. The duplicate job guard only applies to active `rpg.turn` jobs with the same session id and command text.
