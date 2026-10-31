# People's days: the world's people keep their routines

## What the player experiences

The people of the world keep their days. The stallholder sells at her stall by day and argues prices over supper at
the tavern in the evening; the captain patrols the road in the morning and keeps order in the square in the
afternoon. Arriving somewhere finds whoever their day has there, and looking around says what they are doing. Someone
the hero is with does not vanish mid-scene: they stay until their day turns, and the hero sees them go ("Mira leaves
for Rusty Flagon Tavern.") or someone come ("Captain Aldric arrives, keeping order in the square."). Companions go
where the hero goes.

## Rules

- **The day is the world's.** A world authors each named person's day as steps (`canon.routines`: from which hour to
  which, where, doing what; a step past midnight wraps). The launch compiles it into the world model
  (`world_model.routines`). A step naming a place the world lacks is not followed.
- **One clock.** Whereabouts follow the campaign clock (`time.md`); the world tick (pipeline step 6) works them out
  for the turn's new time (`rules/routines.py`, pure).
- **Away from the hero**, a person is where their day puts them at the hour.
- **In the scene with the hero** (the presence recorded where the hero stands), a person stays until their day turns
  to its next part: the clock crosses into another of their steps, or a whole day goes by. Then they go where it
  sends them. So an opening, a conversation or a story keeps the people in it.
- **No routine:** a person stays where they are (the index), or where the world put them.
- **Companions** are with the hero, whatever their day says.
- **Who is present** at a place is who is there: travel's arrival, a defeat's waking place and the world tick all ask
  the same rule, at the time the hero is there.
- **Time passing on its own** (`POST /api/rpg/campaigns/{id}/spatial-ticks`, 1 to 12 ticks) is a `world_tick` turn
  with the recap "Time passes in <place>." and the comings and goings.

## State it changes

`WhereaboutsChanged` (each person's place and activity, in the `npcs` section's index `simulation_state.npc_index`),
`PresenceChanged` (who is present where the hero is, the scene and its actors).

## What the narrator is told

"Here: Bran (keeping the tavern), Mira." on arrival and when looking; the comings and goings after what the hero did.

## Scenarios

The starter world's day: going to the market at 08:05 finds Mira there (her day freed her once the hero left the
tavern) and not Aldric (on the road); at 14:05 Aldric arrives in the square; at 16:05 Mira leaves for the tavern, where
the hero finds her watching the common room (`test_the_worlds_people_keep_their_day`). Ticks with no player action are
a committed `world_tick` turn, and the spatial state shows Aldric patrolling the road
(`test_time_passing_on_its_own_is_a_world_tick_turn`).

## Out of scope

Goals biasing what people say and offer, events from pressures and the surfacing budget (RQ-4.3, RQ-4.4); people moving
on the tactical grid between their places (their cells stay in the map-instance snapshots); routines for worlds that
author none (RQ-4.1 generates them).

## As built (RQ-4.3: goals)

The goals a world's routines author for a person (`NpcGoal`: summary, priority, topics) bias what they say and offer
(`rules/dialogue/plan.py`): the plan's goals list theirs first, those the hero's words touch ahead, then by priority,
then the character's own; of the quests they could offer, the one closest to the hero's words and then to their
most pressing goal is offered (before, the first in the log); and a hero who asks about what one of their goals is
after ("any trouble with the wolves?") is offered the quest that answers it, without asking for work. The starter
world authors goals for ten of its people.

## Goals pursued: beats and rumours (evolution roadmap EV-4)

A goal may hold **beats**, the steps its person takes toward it, in order. Each has a chance a day and a condition
(facts that hold, a place the hero has been, a day of the campaign); reached, it may set facts (not known to the hero
yet), take its person to a place they keep to from then on (or away for good), and send word about. On each day the
clock crosses (the last three of a long stretch away), the world tick rolls each goal's next ready beat, seeded by
the campaign, the day and the beat, at most three a day (`rules/routines.daily_beats`, `BeatAdvanced`). A beat never
takes away a protected person (a companion, an open quest's giver or a person its steps need): it waits. The game
master may bring the next ready beat forward (`gm_beat`).

The word is a rumour (`rules/rumours.py`, `RumourSpread`), told at the beat's places (by default where its person
keeps and the goal's place). The hero hears it from someone there asked for news (the dialogue plan's `news` topic,
offered only while there is word to tell), buys it where information is sold (economy.md), or hears it by being there
when it happens (`RumourHeard`); then the facts the beat set are known, and the journal lists the word heard. A fact
a beat sets fires its world's `fact_effects` as a quest's does. Aurelia authors eleven beats over nine people.
Scenarios: `test_beats_and_rumours.py`, `test_goal_beats.py` (200 turns, at least eight beats reached and heard).
