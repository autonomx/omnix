# RQ-5.6 Encounters (stretch): creatures act like themselves, and fighting is not the only answer

## What the player experiences

Wolves flee when badly hurt; bandits call for help; a guardian never leaves its post. Some encounters can be talked
down or slipped past.

## Rules

- Behaviour (authored, RQ-2.0 `bestiary[*].behaviour`; default `fights`):
  - `flees_when_hurt`: below 30% HP, the creature tries to flee (same flee rule as the hero);
  - `calls_allies`: once per fight below 50% HP, a seeded roll (50%) adds one creature of the same kind;
  - `guards`: never pursues beyond its location; leaves the fight if the hero leaves the location;
  - `ambushes`: acts first in the first round.
- Negotiation: an intelligent creature or NPC hostile can be persuaded or intimidated (RQ-5.2) at hard difficulty
  before blows are traded; success ends the encounter without loot or XP but with a relationship change.
- Stealth: a sneak check against the highest creature `defense` − 2 avoids the encounter.

## State it changes

`CombatantFled`, `CombatantJoined`, `CombatEnded`, plus check outcomes.

## Scenarios

A wolf flees at low HP; a bandit calls an ally; a guard does not pursue; a negotiation ends a fight; sneaking past.

## Out of scope

Morale for groups, terrain-based tactics beyond the grid.
