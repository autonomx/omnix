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
boss, and no fitting creature means no offer yet.

## As built (RQ-5.6, part 2: the road, slipping past, talking down)

A dangerous road is dangerous (`rules/pressures.py` `road_encounter`): arriving where no one lives, in a region whose
pressure is above 40, a seeded chance of the severity above 40 (Aurelia's roads at 70: three journeys in ten) puts
one of the pressure's creatures in the hero's way, no stronger than a level above them and never the world's boss;
both the typed journey and the map's (`session/turn/resolution.py` `met_on_the_road`). The creature bars the way
(`fight(action="confront")`) and the hero chooses first, unless it ambushes. Before any blow is traded, the hero may
slip past (a sneak against the foes' best defence less 2, at least 5) or talk it down (persuade or intimidate, hard:
16), routed from the check grammar (`planning.py`); a person or a creature that speaks only (`speaks`, authored or
derived from its lore: bandits, knights, the oath-bound), the others "will not be talked to". Success ends the
encounter (`evaded`, `talked_down`: "You go on your way; no blow was struck."), with the check's own experience and,
for a person, its regard; failure spends the hero's turn. Once blows are traded it is a fight: no slipping away or
talking now. The grammar also reads "reason with", "talk it down", "parley", "negotiate with" as persuading. Found
with it: a check easier than the easiest difficulty had no experience to pay and raised an error.

## As built (RQ-7.7 part 2: where creatures are met)

A creature is met where it lives (`rules/combat/fight.py` `_met_here`): in the wild, where no one lives
(`routines.is_wild`, the road encounter's own test), or at the place a quest the hero has taken sends them to defeat
it (the Rusty Flagon's cellar rats). Anywhere else "I attack the Echo Wolf" is refused: "No Echo Wolf is here. The
world's creatures keep to the wild, where no one lives." Before, any creature of the bestiary could be fought
anywhere (a wolf in the guild hall). The playthroughs, the balance simulation, the latency harness and the Aurelia
golden now meet their creatures in the wild (Skybridge Pass, the Northern Road, Black Rain Station Interior); the
balance bands still hold.
