# RQ-5.1 Stakes: losing costs something, and fleeing is a choice with a price

## What the player experiences

Losing a fight is a setback, not the end: the hero wakes later at the last place they rested, hurt, lighter in the
purse, perhaps without something they carried, and the world moved on meanwhile. Injuries linger until treated or
rested off. Fleeing works more often than it fails, but it costs: a parting blow, a dropped item, a lost chance at
the loot. A campaign can be started in **hardcore** mode, where defeat ends the hero's story.

## Rules

- **Defeat** (hero HP reaches 0, standard mode):
  - the fight ends; the creatures keep the field;
  - the hero wakes at the last rested location (`rest_point`, set by lodging, a night's camp or the opening); with
    no rest point, at the opening location;
  - in-game time advances 8 hours (the world ticks for that span, RQ-4.5);
  - HP is set to 25% of max, and the condition `battered` (−2 to attack and checks) lasts until a full rest;
  - coin: lose 20% of the purse, rounded down to whole copper, at least 1 copper if the purse is not empty;
  - item: with a 50% seeded roll (`defeat.item_loss`), lose one unequipped, non-quest item (the most valuable by
    shop price); equipped gear and quest items are never lost;
  - the defeat is recorded (`defeats` counter, journal entry), and companions present are `battered` too.
- **Defeat (hardcore)**: the campaign is marked `ended` (`ended_reason: defeated`), further turns are refused with
  a message, and the journal closes with an epilogue beat. Rewind (RQ-5.7) is disabled in hardcore campaigns.
- **Injuries**: a hit that takes more than 40% of max HP in one blow adds `wounded` (−1 to attack, healing halved)
  until healed by a potion, a healer's service or two full rests.
- **Flee**: d20 + agility modifier vs 10 + the fastest hostile's initiative bonus × 2. On success the fight ends
  and each hostile that could act gets one free attack at disadvantage (roll twice, keep the lower). On failure the
  hero loses the turn. Fleeing forfeits the fight's loot and XP.

## State it changes

`HpChanged`, `ConditionAdded`/`ConditionRemoved`, `CoinChanged`, `ItemRemoved`, `LocationChanged`,
`TimeAdvanced`, `CombatEnded`, `CampaignEnded` (hardcore), `JournalEntryAdded`.

## What the narrator is told

The outcome as facts: "defeated by {creature}; woke at {rest point} {hours} later; lost {coin}; lost {item}";
conditions gained. The narrator may not soften or contradict a loss.

## Scenarios

Fight to defeat (standard): purse −20%, HP 25%, location = rest point, `battered`, time +8 h. Hardcore defeat:
campaign ended, next turn refused. Flee success with a parting blow; flee failure; a wound from a heavy blow cured
by a potion.

## Out of scope

Permanent stat loss, corpse runs, multiple save slots for hardcore.
