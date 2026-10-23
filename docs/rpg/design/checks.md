# RQ-5.2 Checks: try things outside a fight, see the roll, and fail forward

## What the player experiences

Persuading a guard, sneaking past a camp, climbing a wall, picking a lock or recalling lore is decided by a visible
roll: the screen shows d20 + skill against the difficulty and the margin. Failure changes the situation instead of
stopping the story: the guard grows suspicious, the climb costs time and a scrape, the lock jams but the noise draws
someone.

## Rules

- A check is planned (step 3) when the intent is one of: `persuade`, `intimidate`, `deceive`, `sneak`, `climb`,
  `pick_lock`, `recall_lore`, `search`, `notice`.
- Roll: `d20 (seeded: check.<kind>.<target>) + skill rank + attribute modifier + situational modifiers`
  (conditions, tools, relationship: +2 trusted, −2 hostile).
- Difficulty: trivial 5, easy 10, moderate 13 (default), hard 16, very hard 19, heroic 22. The world model can set a
  difficulty for a target (a locked door, a guarded gate); otherwise moderate.
- Outcome by margin: ≥ +5 strong success (extra benefit), ≥ 0 success, −1 to −4 success at a cost (time, HP,
  suspicion, noise), ≤ −5 failure with a consequence. A natural 20 is at least a success; a natural 1 at most a
  success at a cost.
- Retrying the same check on the same target in the same scene is at +2 difficulty and costs time.
- Success grants skill XP (RQ-5.3): 10 for moderate, scaled by difficulty.

## State it changes

`CheckResolved` (recorded for the outcome card), plus the consequence's changes: `RelationshipChanged`,
`KnowledgeShared`, `LocationChanged`, `ItemAdded`, `HpChanged`, `TimeAdvanced`, `PressureChanged` (noise raises
alertness), `SkillXpGained`.

## What the narrator is told

The check (kind, roll, total, difficulty, margin band) and its consequence. The roll is shown in the outcome card;
the narration describes it.

## Scenarios

Persuade a shopkeeper for a discount (success at a cost: the price drops, relationship −1); sneak past a guard
(strong success); pick a lock and fail (noise raises a pressure); recall lore about a creature (success reveals its
weakness).

## Out of scope

Opposed checks between NPCs, group checks.
