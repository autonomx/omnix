# Intent held-out labels to review (2026-10-26)

The intent gate (M2) scores the game against the frozen held-out set
(`resources/benchmarks/rpg/intent_corpus`). Two groups of its labels disagree with what the game now does on
purpose. They are listed here for the owner's spot check, because only the owner may change a frozen label (the set's
hash is part of each measurement). Neither group is fixed in code.

## Labelled "not stateful" where the action changes the campaign (11 items)

M2's false-stateful rate counts these. The upper bound was 2.2% at e78e10bd9f, against a target of 1.0%. Every
false-stateful turn in that run is one of these 11:

| Item | World | Input | Label | What the game does |
|---|---|---|---|---|
| held-0052 | aurelia | I ready my Gateborn Compass | equip, not stateful | equips it |
| held-0254 | aurelia | use the lantern bread | use_item, not stateful | eats it |
| held-0397 | aurelia | use my bread | use_item, not stateful | eats it |
| held-0489 | starter | wield the torch | equip, not stateful | wields it |
| held-0752 | starter | I want to sell my torch | sell, not stateful | sells it |
| held-0753 | starter | I want to sell my travel cloak | sell, not stateful | sells it |
| held-0347 | aurelia | search the area for anything hidden | manipulate, not stateful | a search check, which earns investigation experience |
| held-0597 | starter | Bran, do you know any good stories? | ask, not stateful | does the tavern rumor quest's step ("ask Bran or Mira which rumor is true") |
| held-0618 | starter | aks the serving girl about the rumor | ask, not stateful | the same quest step |
| held-0627 | starter | could I get a rumor here? | ask, not stateful | the same quest step |
| held-0646 | starter | what's the price of a rumor? | ask, not stateful | the same quest step |

**Suggested:** mark the six equip, use and sell items stateful; they name a deed. For the search and the four rumor
items, either mark them stateful, or decide that a quest step done by a question, and a check's skill experience,
should not count as the player's stateful act (the eval would then exclude them).

## "The server" and "the serving girl" for Mira (11 items)

The corpus calls the starter town's Mira "the server" or "the serving girl", as the engine's old copy of the town
did. In The Market Road her lore is a "curious local informant and would-be companion" who sits at the Rusty Flagon.
She serves no one, so nothing in the world names her that way, and the game reads "the server" as the Flagon's
innkeeper, Bran.

The items are held-0452, 0606, 0618, 0624, 0658, 0663, 0713, 0767, 0768, 0773 and 0782. Inputs include "who is the
serving girl?", "I kick the server" and "say hello to the server".

**Suggested:** either relabel these to Bran, or call them ambiguous and drop them; or, as the world's author, give
Mira the serving-girl calling in The Market Road's lore, and the game will read them as labelled.
