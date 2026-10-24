# Combat (RQ-2.6): one rule, from the campaign to the changes

## What the player experiences

The hero attacks a creature the world knows ("I attack the Echo Wolf") or someone present ("I attack Bran"), and a
fight begins: everyone rolls for
initiative, and whoever is quicker than the hero strikes first. Each turn the hero strikes or tries to break away,
then everyone else whose turn comes before the hero's next acts: creatures strike the party, companions strike the
creatures. A won fight earns the creatures' experience and whatever they drop; a lost one is the setback of
[stakes.md](stakes.md); a fight fled from yields nothing.

## Rules

- **Who can be fought.** A creature of the world's bestiary (the campaign's creature definitions), or a person
  present. A person's numbers come from what they do: a fighter (guard, soldier, captain, hunter, scout...) level 3,
  22 health, defence 13, armour 1, 2-6 damage, +3; someone hardy (smith, porter, innkeeper...) level 2, 16, 11, 1-4,
  +1; anyone else 10 health, defence 10, 1-3. The hero does not turn on a companion (refused, no turn taken).
  Anything else (an object) is not this rule's: the turn takes the older path. There is no default foe.
- **Attacking someone** costs their trust (-40) and that of everyone present who saw it (-15), on the -100 to 100
  scale dialogue reads (wary below 0); the play screen's relationships list shows it.
- **The start.** The participants are the hero, the companions in the party, and the creature. Initiative is a
  seeded d20 plus each one's initiative bonus; ties go by id. Foes ahead of the hero act before the hero's first
  blow.
- **A blow.** A seeded d20 plus the attacker's accuracy, less any condition penalty (battered 2, wounded 1), against
  the target's defence; a hit deals a seeded roll in the attacker's damage range less the target's armour, at least
  1. The hero's and companions' numbers are their equipment's; a creature's are its definition's.
- **A heavy blow** (more than two fifths of a party member's maximum health at once) leaves them wounded.
- **Breaking away.** A d20 plus the hero's initiative bonus against 10 plus twice the quickest foe's; on success
  each foe still standing strikes once at disadvantage (a parting blow), and the fight ends; on failure the turn is
  spent.
- **Others' turns.** After the hero acts, everyone whose turn comes before the hero's next acts, each striking the
  first foe standing. Start-of-turn conditions (a stun from a weakness) apply as turns pass.
- **The end.** Every foe down: victory; a person beaten yields (alive), for no experience or spoils; each creature
  earns the experience of each (its `xp_value`, or 25 a level where the
  world gives none), and each loot drop on its seeded chance into the pack. The party down: defeat (stakes.md). Fled: nothing.
- **In a fight** the hero strikes, breaks away, defends (their defence +2 until their next turn), or uses something
  carried (a potion), which spends their turn
  before the others act; the party's health is the party's, so a heal between blows holds. Leaving, resting,
  waiting, trading, talking it over or picking things up is refused in the game's own words; the turn is counted
  and nothing else changes.
- **Time.** A combat turn takes a minute of in-game time and presses on needs as a standard turn; a lost fight
  takes 8 hours.

- **On the grid** (the tactical routes) the fight is the same fight, seen on the map: each command is a
  structured-action turn whose only token is the campaign revision the player saw. A move spends the hero's
  movement for their turn (60, a fresh allowance each time the turn comes round; a square of open ground costs 10)
  and is the map's change, committed with the turn; an attack is the fight's blow, with the target's cover adding to
  its defence (half +2, full +5) and a blocked line of sight or a target out of reach refused. A refused grid command
  takes no turn. Grid turns tell no narrator: their lines are the game's own.

## State it changes

`CombatAdvanced` (the combat section as the turn leaves it), `RegardChanged` (attacking a person), `HpChanged`, `CompanionHpChanged`, `ConditionsChanged`
(wounds; battered on defeat), `ExperienceGained` and `LevelReached`, `ItemAdded` (loot), and on defeat
`DefeatRecorded`, `PurseChanged`, `ItemRemoved`, `LocationChanged`, `PresenceChanged`, or `CampaignEnded` in
hardcore; `TurnCounted`, `TimeAdvanced`.

## What the narrator is told

The blows in the order they fell, with what each left; wounds; the end of the fight and what it earned or cost.
The narrator may not add blows, damage or combatants.

## Scenarios

A fight to victory (experience and loot); a lost fight is a setback; hardcore defeat ends the campaign; fleeing
ends the fight with parting blows; a creature the world does not know is not fought by this rule; fighting a person
costs trust, and beaten they yield for nothing; a companion is not turned on; defending raises the hero's guard.

## Out of scope (RQ-2.6 part 2)

Abilities and their costs, ammunition, companion commands mid-fight, reactions on the grid (a blow at a foe moving
out of reach), creatures placed on the grid when a fight starts, guards joining a fight in their town.
