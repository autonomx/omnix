# Items and rest (RQ-2.4)

## What the player experiences

What the hero carries can be used: a potion heals and closes a wound, food eases hunger, a drink eases thirst.
Things can be put down where the hero stands and picked up again later, or given to someone. A night's sleep, in a room paid for or at a
camp in the wild, restores the hero; a short rest takes the edge off.

## Rules

- **Using an item** (one of the stack is used up; ten minutes):
  - a potion (the world's item type `potion`, or a healing item): heals 30% of max HP, at least 10, halved while
    wounded, and closes a wound (stakes.md);
  - food (`food`): hunger −25;
  - a drink (`drink`): thirst −30;
  - anything else: refused, "the {item} is not something you can use like that", with no time passed.
- **Putting down and picking up** (no time): one of a stack, or the number the player says ("two"). What lies on the
  ground stays where it was put down.
- **Giving** (no time): one of a stack, or the number said, goes to someone here, who trusts the hero a little
  more for it (regard +5). Unnamed, it goes to the one person here; with more, the game asks to whom. To someone
  not here, or with nothing like it carried, it is refused. A gift is no sale: nothing is paid for it.
- **Wearing and wielding** (no time): a weapon is taken up in the main hand (a shield in the off hand), armour,
  a helmet, a cloak or a ring goes on its place, and a tool (a compass, a lantern, a torch) is held to hand, each
  taking the place of what was there; it stays in the pack. Food and potions are not worn. Asking for what is already worn changes nothing. Taking something off puts it
  away. Gear that leaves the pack (dropped, given, sold, used up) is no longer worn.
- **One gear record** (document version 8): what is worn is the store's (`inventory_state.equipment`, by slot:
  `main_hand`, `off_hand`, `body`, `head`, `cloak`, `ring`, `tool`), which combat reads; the play screen's sheet lists it
  ("Weapon", "Cloak", ...). The old third record (`player_state.inventory`) is gathered into the store.
- **The loadout** (the play screen's pack) uses, equips, takes off and drops as structured-action turns: the same
  rules, their lines the game's own (no model call); what a rule refuses takes no turn. In a fight, an item is used
  by saying so, so the others act after it.
- **Resting**:

  | Rest | Takes | Fatigue | HP | A full rest |
  |------|-------|---------|----|-------------|
  | a room paid for (a reserved lodging service here) | 8 h | −60 | +50% of what is missing | yes; the room is used |
  | a camp, where no one rents rooms | 8 h | −40 | +25% of what is missing | yes |
  | a while ("rest", no sleep or camp) | 1 h | −15 | none | no |

  Where rooms are for rent and the hero has none, sleeping is refused with the offer: a bed costs coin here.
  A **full rest** makes the place the hero's rest point, ends `battered`, and brings a wound a night nearer healing.
  Stamina and mana (what abilities spend) come back in full with a night's rest, and by health's share with a short
  one (`ResourcesChanged`).
- Needs rise once per turn for a rest's turn (the `rest` survival profile); time passes on the clock (time.md).

## State it changes

`ItemRemoved`, `HpChanged`, `NeedsChanged`, `ItemDropped`, `ItemPickedUp`, `ItemEquipped`, `ItemUnequipped`,
`ConditionsChanged`, `RegardChanged` (a gift), `RestTaken`, `ServiceUsed`, `TimeAdvanced`.

## What the narrator is told

The facts: what was used and what it did, what was put down, picked up or given and to whom, how long the rest was and what it
restored.

## Scenarios

Drink a healing potion when hurt; eat bread when hungry; put down one of two loaves, leave, return and pick it up;
give a dagger to the guide (it leaves the pack, unworn, and the guide's regard rises); give with two people here
and no one named (asked to whom); rent a room and sleep, twice on two nights; camp in the wild; try to sleep in the village without a room.

## Out of scope

Crafting, salvage and modifications (the loadout's older crafting had no world catalog and no caller on the play
screen; it was deleted in RQ-2.4 part 3), waterskin charges, spoilage.
