# RPG intent corpus v1 (RQ-0.4)

2,000 player inputs over three worlds, labelled with what the player means. Built 2026-10-23 by
`scripts/rpg_intent_corpus_build.py`; measured by `scripts/rpg_intent_eval.py`.

**Labels are model-labelled and pending the owner's spot check** (`"labelled_by": "model"`,
`"review": "pending_owner_spot_check"` on every row). Corrections are edits to the JSONL rows.

## Files

| File | Rows | Use |
|---|---:|---|
| `dev.jsonl` | 800 | Development: tune the grammar and prompts on this set only |
| `held_out.jsonl` | 1,200 | Frozen, for gates only. Its SHA-256 is pinned in `scripts/rpg_intent_eval.py`, which refuses to run when the file changes; a change is a re-freeze in a reviewed commit |
| `catalog.json` | — | Each world's scenes (where the player stands, who is present, exits, offers) and entities (id, kind, the names a player uses, the ids the engine may report for it) |

Held-out mix: 902 not stateful (at least 800 required), 919 with a target entity (at least 700). The split is
stratified by world and action family.

## A row

```json
{"id": "held-0001", "world": "aurelia", "scene": "village", "input": "buy a healing potion",
 "action_family": "buy", "target_entity": "npc:brindle-gearwing:healing-potion", "stateful": true,
 "tags": [], "labelled_by": "model", "review": "pending_owner_spot_check"}
```

Worlds: `aurelia` (scenes `grove`, `village`, `guild`), `vesper-9` (`docks`, the "Black Rain Rising" opening at
Tidebreak Docks) and `starter` (the starter town: `tavern`, `market`). Tags: `question`, `hypothetical`, `negation`,
`multi_step`, `typo`, `price`, and `trap:<word>` for the substring traps (`trap:use` "useful", "because";
`trap:rest` "forest", "interesting", "restless"; `trap:hit` "white"; `trap:rent` "current"; `trap:eat` "great";
`trap:take` "mistake"; `trap:inn` "dinner").

## Label policy

**Action family** (closed set): `look`, `inspect`, `move`, `talk`, `ask`, `decline`, `buy`, `sell`, `attack`,
`flee`, `defend`, `take`, `drop`, `give`, `use_item`, `equip`, `unequip`, `manipulate`, `rest`, `wait`, `quest`,
`practice`, `party`, `status`, `clarify`. They follow the engine's action kinds (`SUPPORTED_ACTION_KINDS` in
`rules/interactions/semantic_actions.py`, the service kinds, travel, dialogue, combat, quests, practice, rest and
the status report), grouped by what the player is trying to do:

- `look`: take in the scene ("look around", "where am I?", "who's around?"). `inspect`: one thing or person.
- `talk`: say something, to someone or to the room, that asks for nothing. `ask`: a question or a request for
  information, including prices ("how much is a room?") and hypotheticals ("what would happen if I attacked
  Orik?"). `decline`: refusing or holding back ("no thanks", "I won't buy anything yet").
- `buy` includes paying for lodging, meals, drinks, repairs and paid information. `rest` is resting or sleeping
  without paying for it; `wait` is letting time pass.
- `quest` is taking on a quest; `practice` training a skill; `party` asking someone to join.
- `status` is a question about the player's own sheet (inventory, purse, quests, level, health).
- `clarify`: the input cannot be acted on without asking what is meant ("do it", "buy", "use it").
- A multi-step input is labelled by its first step.

**Target entity**: the one entity the action is directed at, as a catalog id, or null. For `talk` and `ask` it is
the person addressed when there is one, otherwise what is asked about; for `buy` the offer or item; for `sell`,
`drop`, `give`, `use_item`, `equip` and `unequip` the item; for `move` the destination; for `attack` the creature or
person; for `quest` the quest; for `practice` the skill (`skill:<name>`); for `party` the person.

**Stateful**: whether the correct handling changes campaign state beyond the passage of time: place, purse, pack,
equipment, party, quests, skills, hit points, a fight, or fatigue relieved by rest. Questions, looking, talking,
waiting, status, declining and clarifying are not stateful. Some labels depend on the scene: buying where nobody
sells it, or with an empty purse (Vesper-9's opening), is `buy` and not stateful; selling where nobody buys is not
stateful; re-equipping what is already equipped is not stateful; using a tool that is not used up (the compass) is
not stateful, eating food is. A question or a talk is stateful when the game's handling of it changes a quest or a
skill: a question that completes a quest's step (asking after the rumor the tavern quest asks for), a search check
whose skill rises. Readying something the hero carries and has not equipped is stateful (equipment).

**Re-freeze, 2026-10-29 (owner decision).** Eleven held-out items labelled not stateful name a deed the game does on
purpose: held-0052, 0254, 0397, 0489, 0752 and 0753 (equip, use, sell) and held-0347, 0597, 0618, 0627 and 0646
(a search check; a question that completes the tavern quest's rumor step). They are relabelled stateful, their
`review` is `owner_relabelled_2026-10-29`, and the pinned SHA-256 is the new file's
([label review](../../../../docs/measurements/rpg-intent-label-review-2026-10-26.md)).

## Known limits

- Inputs come from templates over each world's real people, places, items, offers and quests, filled at random
  with a fixed seed; phrasing is less varied than live play.
- Vesper-9's labels use its canon ids (`ent:actors:*`, `ent:places:*`). On 2026-10-23 the engine launches
  Vesper-9 with an empty world model (no people, places or offers), so its targets cannot be resolved today.
- Labels follow this policy; a reviewer who disagrees with the policy should change the policy here first.
