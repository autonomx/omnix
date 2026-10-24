# RQ-5.4 Quests: several steps, real branches, and the possibility of failing

## What the player experiences

A quest has steps the journal shows one at a time, sometimes with two ways forward ("convince the warden, or find
the back way in"). Quests can fail: a deadline passes, someone dies, the player sides against the giver. People in
the world offer quests in conversation (a `QuestOffered` from the dialogue plan), and the world's pressures create
side quests ("the roads are dangerous: clear the wolves from Skybridge Pass").

## Rules

- Quest model: `steps[]`, each with `conditions` (reach a place, talk to someone, hold an item, defeat a creature,
  pass a check, a pressure below a value), optional `branches` (alternative steps that complete the same stage),
  optional `deadline` (in-game hours) and `fail_conditions`.
- Progress is evaluated after every turn's changes (step 5) and world tick (step 6): a step completes when its
  conditions hold; the quest completes when its last stage does.
- Failure: a deadline passes or a fail condition holds → quest `failed`, a journal beat, and the giver's
  relationship −10 (unless the failure was the giver's own doing).
- Rewards as authored (coin, items, XP, relationship); defaults by step count when not written.
- Pressure side quests: when a pressure reaches 60 severity and no active quest targets it, a quest is offered by a
  person in the pressure's region whose role fits (guard, guild, elder) with a lever as its goal ("defeat 3 echo
  wolves"). At most one open pressure quest per pressure; ids are seeded (`next_turn_id("rpg.quest.arc")`).

## State it changes

`QuestOffered`, `QuestAccepted`, `QuestStepCompleted`, `QuestBranchChosen`, `QuestCompleted`, `QuestFailed`,
reward changes (`CoinChanged`, `ItemAdded`, `XpGained`, `RelationshipChanged`).

## Scenarios

Offer in conversation → accept → two steps → reward; a branch taken; a deadline failing a quest; a pressure crossing
60 producing a side quest that defeating creatures completes and that lowers the pressure.

## Out of scope

Quest chains across campaigns, procedurally generated main quests.

## As built (RQ-5.4, part 1)

A world authors a quest's `steps` (`rules/quest/progress.py`): stages done in order, each `all_of` conditions or
`any_of` alternatives (the branches); a condition is `reach` a place, `talk` to someone (a `DialogueExchanged` this
turn; with `about`, the hero's words must touch one of its words), `hold` an item, `defeat` a creature `count` times (tallied from won fights in `progress.counts`) or pass a
`check` (a `CheckResolved` not failed, of that kind and target). `_quests_advance` judges them after the turn's
changes and world tick (`session/turn/run.py`), and after a `world_tick` turn, so a deadline can run out while the
hero is away. The changes: `QuestProgressed` (the tallies), `QuestStepCompleted` (the stage, the branch taken and the
next objective, which the log shows), then `QuestStatusChanged` completed with the rewards (`quest_rewards`: coin,
items, and the XP named or 50 per step), or failed when `deadline_hours` have passed since `accepted_at_minute`
(stamped when the quest becomes active, at the opening for the quest a campaign starts on), with the giver's regard
−10 (`RegardChanged`). A quest without steps advances by its places, as before (`arrival.py`). On a dialogue turn
what the exchange led to is said after the person's line (`aftermath`). The starter world authors steps on three
quests (the tavern rumor, ask Bran or Mira; the cellar rats, three then the report; Elara's job, with a day's
deadline). A quest offered in conversation (RQ-2.2) fails against whoever offered it. Not yet: `fail_conditions`
beyond the deadline, a pressure below a value, and pressure side quests (part 2).

## As built (RQ-5.4, part 2)

A pressure's `levers` have a grammar (`world_play_sections.PressureLever`, checked at release against the bestiary
and the quests): `defeat:<creature id>` pulls once for each such creature felled, `quest:<quest id>` when that quest
is completed, each by its amount (`lower` or `raise`). After the quests have moved, `rules/pressures.py`
`lever_pulls` reads the turn's changes and `world.causal_runtime.pull_levers` moves the severities as one replayable
`lever_pulled` event at the runtime's tick (the history still replays to the same state; the next pressure tick
judges statuses, so a pressure eased below its resolution threshold resolves); `PressuresMoved` (49 types) carries the
runtime the pull left. `pressure_offers` then raises a side quest for the pressure of the hero's region when it is at
60 or more and no open quest answers it, offered by a person with the hero whose role fits (a guard, a captain, a
watch, a guild's, an elder...): defeat the strongest of its `defeat:` lever creatures below the hero's level, else
one of their level, never a boss, none fitting no offer yet (encounters.md; as many as push it back by 20, at most 3), then a word with the giver; 10 silver and the experience of its
steps. `QuestOffered` carries the new quest's row; accepting a title offered again takes the open offer. None of it
runs on a refused turn, a question back or a rewind (`session/turn/run.py` `turn_consequences`). Before this nothing
pulled a lever, so a pressure only ever rose. The starter world's levers were prose ("defeat the bandits at the
mill") and are now in the grammar (the quarry crate that raised its pressure had no deed behind it and is gone).
The balance simulation does quests of steps and takes a conversation it cannot play (no model) as answered; with
side quests the purse and the quests done are inside their bands. Not yet: a pressure below a value as a step
condition, fail conditions beyond the deadline.

## As built (with RQ-5.5)

A side quest from the pressures is offered one at a time and at most one a campaign day (`PRESSURE_QUEST_EVERY`,
from the last one's `offered_at_minute`): the hero's region's pressure first, else the most severe elsewhere, so a
hero whose home is safe is still asked about the roads beyond it. A `defeat:` lever pulls only the pressure of the
region the creature fell in (a world's derived pressures list every creature in every region); a `quest:` lever is
the quest's, wherever it was done.

