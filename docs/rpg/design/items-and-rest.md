# Items and rest (RQ-2.4)

## What the player experiences

What the hero carries can be used: a potion heals and closes a wound, food eases hunger, a drink eases thirst.
Things can be put down where the hero stands and picked up again later. A night's sleep, in a room paid for or at a
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
- **Resting**:

  | Rest | Takes | Fatigue | HP | A full rest |
  |------|-------|---------|----|-------------|
  | a room paid for (a reserved lodging service here) | 8 h | −60 | +50% of what is missing | yes; the room is used |
  | a camp, where no one rents rooms | 8 h | −40 | +25% of what is missing | yes |
  | a while ("rest", no sleep or camp) | 1 h | −15 | none | no |

  Where rooms are for rent and the hero has none, sleeping is refused with the offer: a bed costs coin here.
  A **full rest** makes the place the hero's rest point, ends `battered`, and brings a wound a night nearer healing.
- Needs rise once per turn for a rest's turn (the `rest` survival profile); time passes on the clock (time.md).

## State it changes

`ItemRemoved`, `HpChanged`, `NeedsChanged`, `ItemDropped`, `ItemPickedUp`, `ConditionsChanged`, `RestTaken`,
`ServiceUsed`, `TimeAdvanced`.

## What the narrator is told

The facts: what was used and what it did, what was put down or picked up, how long the rest was and what it
restored.

## Scenarios

Drink a healing potion when hurt; eat bread when hungry; put down one of two loaves, leave, return and pick it up;
rent a room and sleep, twice on two nights; camp in the wild; try to sleep in the village without a room.

## Out of scope

Equipping and loadout (they keep their structured actions until RQ-7), crafting, waterskin charges, spoilage.
