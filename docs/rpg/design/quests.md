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
