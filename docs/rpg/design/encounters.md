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

## As built (RQ-5.6, part 1: behaviour)

`rules/combat/fight.py` `_behaves`, on a creature's turn instead of a blow: `flees_when_hurt` tries once, below 30%
of its health, on the hero's own rule to break away (a creature that gets away earns nothing; a fight whose foes are
all gone without one falling ends `enemy_fled`, "it yields you nothing"); `calls_allies` calls once below 50%, and
on a seeded even chance one more of its kind joins after it in the turn order (the ally calls no one); `guards`:
breaking away from guardians alone always succeeds, with no parting blows; `ambushes`: first in the first round.
The creature's behaviour reaches the fight from the catalog (`instantiate_campaign_creature`); a world that names
none has one derived from the creature's name and traits (`published_world_setup.derived_behaviour`: Aurelia's Echo
Wolf flees when hurt, its oath-bound Rootbound Knight guards, the face-stealing Glass Wight ambushes, the splitting
Hollow Archon calls allies). The narration states each act ("The Wolf breaks away and flees."). With behaviour the
balance simulation's win rates are inside their bands in Aurelia (0.71 after 100 turns, 0.87 after 500) and late in
the starter world (0.85). Found with it: a pressure's side quest hunted the strongest lever creature up to the
hero's level, which with allies called was more than a match (a level-2 hero fled Bandit Brutes eight times), and
when none fitted it hunted the weakest anyway (level-9 Icefang Wolves for a level-2 hero), and at level 9 the world's
boss (three Hollow Archons): a hunt now takes the strongest below the hero's level, else their equal, never a
boss, and no fitting creature means no offer yet. Not yet: negotiation and stealth (part 2).
