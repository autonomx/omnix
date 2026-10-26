# Time: one clock, and how long things take

## What the player experiences

The day moves on as they play. Looking around takes a few minutes, waiting a while takes half an hour, a night's
sleep lasts until morning, and a lost fight costs hours. The time of day and the weather follow, and coming back
after time away finds the world moved on.

## Rules

- **One clock.** The campaign's in-game time is the simulation's environment (`absolute_minutes`, with its weather
  events and calendar). The play screen shows its copy (`state.world.environment`, `state.world.time`).
- **A tick is 10 in-game minutes.** A turn says how many ticks it took (`TimeAdvanced.ticks`, `.minutes`), and the
  world tick (pipeline step 6) moves the clock by those minutes, the weather with it.
- **Durations on the pipeline** (others keep their older timing until their mechanic moves, RQ-2):

  | Action | Ticks | In-game time |
  |--------|-------|--------------|
  | look, inspect | 1 | 10 min |
  | wait a while | 3 | 30 min |
  | an unclear command (the game asks) | 0 | none |
  | time away (`world_tick`) | 1 per 5 s away, at most 12 | up to 2 h (RQ-4.5 raises it to 24 h at region resolution) |
  | a lost fight (RQ-5.1) | — | 8 h |
  | a night's lodging | — | until 08:00 |

- **Needs** rise once per turn by the turn's survival profile, not per tick; time away raises none.

## State it changes

`TimeAdvanced` (ticks, minutes), `WorldTicked` (the environment, and the causal runtime's sections when the world has
one), and the people's whereabouts and presence at the new time (`routines.md`).

## Scenarios

Look and wait move the clock by 10 and 30 minutes and the play screen's time follows; time away moves it by up to two
hours with no need raised; a clarification takes no time.

## Out of scope

Per-route travel times on the clock (RQ-2.1). Routines that move people by the hour are in `routines.md`.

## As built (RQ-4.4, RQ-4.5: the world's time, and word of it)

The world's pressures move by its time, not its turns (`session/turn/world_tick.py`): the causal runtime ticks once
for each hour the clock crosses in a turn, at most 12 at once (`MAX_PRESSURE_TICKS`): a blow in a fight moves no
pressure, a four-hour climb four steps, a night's sleep eight, and time away its hours, capped (before, every turn
was one step, so a twenty-round fight moved each pressure as much as twenty journeys). When a pressure turns
(escalates, is held in check, ends, or stirs again) word of it reaches the hero in the turn's lines ("Word comes:
Danger on the roads of Starfall March grows worse."), their own region's first, at most two a turn; the recap of
time away says it too. What the hero does to a pressure was RQ-5.4's levers (quests.md).

## As built (journeys further than a road)

A road takes the time the world gives it (30 minutes when it gives none), and a journey to a neighbouring place is
one turn. A place further off is set out for (`session/turn/travel.py`): the hero takes the first road of the
shortest way there by the roads open now ("You set out for The Ruins: the way goes by The Village."), so
each place on the way is arrived at as any other, its people, its quests and what bars a dangerous road
(encounters.md) included; saying it again goes on. A place no open road reaches is refused, as is the place the
hero is in.
