"""A fight, as the turn pipeline plays it (RQ-2.6; docs/rpg/design/combat.md): one pure rule, from the campaign
to the changes.

``fight`` reads the campaign (never writes it) and returns what one turn of a fight does: the combat section as the
turn leaves it, the party's health and wounds, and at the end what the fight earned (the creatures' experience and
drops, from the world's bestiary) or cost (the setback of a lost fight, stakes.md). The blows are seeded, so the same
campaign and command fight the same way.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from app.apps.rpg.foundation.core.determinism import deterministic_rng
from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    CampaignEnded,
    CombatAdvanced,
    CompanionHpChanged,
    ConditionsChanged,
    DefeatRecorded,
    HpChanged,
    ItemAdded,
    ItemRemoved,
    LocationChanged,
    PresenceChanged,
    PurseChanged,
    RegardChanged,
    StateChange,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.ability_use import FightEffect
from app.apps.rpg.rules.player import progression
from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition, instantiate_campaign_creature
from app.apps.rpg.rules.combat.exchange_lines import describe_combat_exchange
from app.apps.rpg.rules.combat.runtime_core import (
    build_initiative_order,
    combat_seed,
    current_actor_id,
    default_target_for_actor,
    deterministic_roll,
    living_enemy_ids,
    living_party_ids,
    participant,
)
from app.apps.rpg.rules.combat.runtime_turns import next_turn
from app.apps.rpg.rules.combat.stakes import (
    BATTERED,
    BATTERED_PENALTY,
    DEFEAT_HOURS,
    DEFEAT_HP_SHARE,
    DEFEAT_ITEM_LOSS_CHANCE,
    DEFEAT_PURSE_SHARE,
    WOUND_RESTS,
    WOUNDED,
    WOUNDED_PENALTY,
    WOUNDING_SHARE,
    is_hardcore,
)
from app.apps.rpg.rules.interactions.equipment_runtime import project_equipment_stats
from app.apps.rpg.foundation.state import access as _sections

SOURCE = "rpg_turn_pipeline_fight_v1"
MINUTES_PER_TURN = 1
GUARD_BONUS = 2  # defending: added to the hero's defence until their next turn
# A creature acting as its kind does (encounters.md): one that flees when hurt tries once, below this share of its
# health; one that calls allies does so once, below this share, and is answered on a seeded even chance.
FLEE_SHARE, CALL_SHARE, CALL_CHANCE = 0.30, 0.50, 50
# Attacking someone: how far they, and everyone who sees it, trust the hero less (combat.md).
ATTACKED_REGARD, WITNESS_REGARD = -40, -15
FOUGHT_BESIDE_REGARD = 2  # a fight won together: each companion still standing trusts the hero more
# pass: the hero's turn went on something else (a potion); ability: one of the hero's, its effect given;
# confront: a foe comes at the hero (the road's danger), and the fight stands at the hero's turn;
# sneak, parley: before blows are traded, slipping past or talking it down (encounters.md)
Action = Literal["attack", "flee", "defend", "ability", "pass", "confront", "sneak", "parley"]
PARLEY_DIFFICULTY = "hard"  # talking a foe down (persuading or intimidating it) is hard (encounters.md)

# A person's fighting numbers by what they do (the world rates its creatures, not its people): combat.md.
_PERSON_NUMBERS = {
    "fighter": {"level": 3, "hp": 22, "defense": 13, "armor": 1, "damage_min": 2, "damage_max": 6,
                "accuracy_bonus": 3, "initiative_bonus": 1},
    "hardy": {"level": 2, "hp": 16, "defense": 11, "armor": 0, "damage_min": 1, "damage_max": 4,
              "accuracy_bonus": 1, "initiative_bonus": 1},
    "townsfolk": {"level": 1, "hp": 10, "defense": 10, "armor": 0, "damage_min": 1, "damage_max": 3,
                  "accuracy_bonus": 0, "initiative_bonus": 0},
}
_FIGHTER_WORDS = {"guard", "soldier", "captain", "knight", "warrior", "mercenary", "sellsword", "watch", "sergeant",
                  "champion", "veteran", "hunter", "ranger", "scout", "bandit", "thug", "enforcer", "duelist",
                  "general", "commander", "warlord", "protector", "gatewarden", "warden", "paladin", "templar"}
_HARDY_WORDS = {"smith", "blacksmith", "porter", "miner", "sailor", "dockhand", "farmer", "woodcutter", "innkeeper",
                "bouncer", "tracker", "guide", "keeper", "sentry"}
# The skill a weapon is fought with, by the words of its name (else a blade's: swordsmanship); progression.md.
_WEAPON_SKILLS = (("archery", {"bow", "longbow", "shortbow", "crossbow", "sling"}),
                  ("magic", {"staff", "wand", "rod", "orb", "focus", "tome", "grimoire"}))


@dataclass(frozen=True)
class FightTurn:
    changes: list[StateChange]
    lines: list[str]  # what the narrator is told: the blows in order, and how the fight stands
    refused: bool = False
    minutes: int = MINUTES_PER_TURN
    ended: str = ""  # victory, defeat, fled, or "" while the fight goes on
    report: dict[str, Any] = field(default_factory=dict)  # the turn's blows, as the play screen and logs read them


# -- the party as the fight sees it -------------------------------------------------------------------------------------
def _player(simulation: Mapping[str, Any]) -> dict[str, Any]:
    return _d(_sections.player_state_of(simulation))


def _hero_hp(simulation: Mapping[str, Any]) -> tuple[int, int]:
    player = _player(simulation)
    pool = _d(_d(player.get("resources")).get("hp"))
    maximum = int(pool.get("max") or player.get("max_hp") or 20)
    return int(pool.get("current") if pool.get("current") is not None else player.get("hp") or maximum), maximum


def _companions(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(row) for row in _l(_d(_sections.party_state_of(_player(simulation))).get("companions")) if _s(_d(row).get("npc_id"))]


def _conditions(simulation: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Each party member's lingering conditions, as stored (copies the fight may add to)."""
    party = {"player": [_d(row) for row in _l(_player(simulation).get("conditions")) if _d(row)]}
    for companion in _companions(simulation):
        party[_s(companion.get("npc_id"))] = [_d(row) for row in _l(companion.get("conditions")) if _d(row)]
    return deepcopy(party)


def _numbers(simulation: Mapping[str, Any], combat: Mapping[str, Any], actor_id: str) -> dict[str, int]:
    row = participant(dict(combat), actor_id)
    if _s(row.get("side")) == "enemy":
        hindered = int(_d(row.get("hindered")).get("accuracy") or 0)  # an ability's hindrance, while it lasts
        return {"damage_min": max(1, int(row.get("damage_min") or 1)), "damage_max": max(1, int(row.get("damage_max") or 3)),
                "accuracy_bonus": int(row.get("accuracy_bonus") or 0) - hindered, "encumbrance_penalty": 0}
    stats = _d(project_equipment_stats(dict(simulation), actor_id=actor_id).get("stats"))
    numbers = {"damage_min": max(1, int(stats.get("damage_min") or 1)), "damage_max": max(1, int(stats.get("damage_max") or 2)),
               "accuracy_bonus": int(stats.get("accuracy_bonus") or 0),
               "encumbrance_penalty": int(stats.get("encumbrance_penalty") or 0)}
    if actor_id == "player":  # the hero's level, attributes and weapon's skill count, not their gear alone (progression.md)
        strength, dexterity = _modifier(simulation, "strength"), _modifier(simulation, "dexterity")
        harder = max(0, strength)
        trained = _skill_rank(simulation, _weapon_skill(simulation))
        numbers.update(accuracy_bonus=numbers["accuracy_bonus"] + (_level(simulation) - 1) // 3 + max(0, strength, dexterity)
                       + trained,
                       damage_min=numbers["damage_min"] + harder, damage_max=numbers["damage_max"] + harder)
    elif _s(row.get("side")) == "party":  # a companion fights as their calling does (combat.md), and with their gear
        calling = _calling_numbers(_d(_d(_d(_sections.world_model_of(simulation)).get("npcs")).get(actor_id)))
        numbers.update(accuracy_bonus=numbers["accuracy_bonus"] + calling["accuracy_bonus"],
                       damage_min=max(numbers["damage_min"], calling["damage_min"]),
                       damage_max=max(numbers["damage_max"], calling["damage_max"]))
    return numbers


def _skill_rank(simulation: Mapping[str, Any], skill: str) -> int:
    """The hero's rank in a skill (0 to 5): the level's choices and practice raise it (progression.md)."""
    return max(0, int(_d(_d(_player(simulation).get("skills")).get(skill)).get("level") or 0))


def _weapon_skill(simulation: Mapping[str, Any]) -> str:
    """The skill the hero's weapon is fought with (the playtest: swordsmanship, chosen twice, counted for nothing)."""
    worn = _l(project_equipment_stats(dict(simulation), actor_id="player").get("equipped_items"))
    words = {word for item in worn for word in _s(_d(item).get("name")).casefold().split()}
    return next((skill for skill, kinds in _WEAPON_SKILLS if words & kinds), "swordsmanship")


def _calling_numbers(person: Mapping[str, Any]) -> dict[str, int]:
    """Someone's fighting numbers by what they do (a guard fights as a fighter, a guide as the hardy)."""
    words = set(_s(f"{person.get('role')} {person.get('name')}").casefold().replace("-", " ").split())
    return _PERSON_NUMBERS["fighter" if words & _FIGHTER_WORDS else "hardy" if words & _HARDY_WORDS else "townsfolk"]


def _level(simulation: Mapping[str, Any]) -> int:
    return max(1, int(_player(simulation).get("level") or 1))


def _modifier(simulation: Mapping[str, Any], attribute: str) -> int:
    return (int(_d(_player(simulation).get("stats")).get(attribute) or 10) - 10) // 2


def _person(simulation: Mapping[str, Any], target_ref: str) -> tuple[str, dict[str, Any]]:
    """The person present the hero means to fight, by id or name: (id, their world record), or ("", {})."""
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    here = routines.present_now(simulation)[1]
    wanted = target_ref.casefold().removeprefix("the ").strip()
    for npc_id in here:
        name = _s(_d(people.get(npc_id)).get("name"))
        if npc_id in people and wanted and (wanted == npc_id.casefold() or (name and _names(wanted, name))):
            return npc_id, _d(people[npc_id])
    return "", {}


def _known_person(simulation: Mapping[str, Any], target_ref: str) -> str:
    """The name of the world's person ``target_ref`` means, by id or by name, wherever they are; "" when none."""
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    wanted = target_ref.casefold().removeprefix("the ").strip()
    if not wanted:
        return ""
    for npc_id, record in people.items():
        name = _s(_d(record).get("name"))
        if wanted == str(npc_id).casefold() or (name and _names(wanted, name)):
            return name or str(npc_id)
    return ""


def _names(text: str, name: str) -> bool:
    """Whether ``text`` names ``name`` as whole words ("Kit" is not in "the kitten")."""
    return re.search(rf"(?<![a-z0-9]){re.escape(name.casefold())}(?![a-z0-9])", text) is not None


def _person_foe(npc_id: str, person: Mapping[str, Any]) -> dict[str, Any]:
    numbers = _calling_numbers(person)
    rank = next(name for name, row in _PERSON_NUMBERS.items() if row is numbers)
    return {"actor_id": npc_id, "enemy_id": npc_id, "npc_id": npc_id, "definition_id": npc_id, "kind": "person",
            "name": _s(person.get("name")) or npc_id, "side": "enemy", "max_hp": numbers["hp"], "tags": [rank],
            **numbers}


def _start(simulation: Mapping[str, Any], enemy: dict[str, Any], *, turn_key: str, confronted: bool = False
           ) -> dict[str, Any]:
    """A fight begins, in its initiative order; a foe that bars the hero's way (``confronted``) waits on them."""
    hp, max_hp = _hero_hp(simulation)
    armor = int(_d(project_equipment_stats(dict(simulation), actor_id="player").get("stats")).get("armor") or 0)
    participants: dict[str, dict[str, Any]] = {"player": {
        "actor_id": "player", "side": "party", "name": "You", "hp": hp, "max_hp": max_hp, "armor": armor,
        "defense": 10 + max(0, _modifier(simulation, "dexterity")) + _level(simulation) // 4
        + _skill_rank(simulation, "defense"),
        "initiative_bonus": 1 + max(0, _modifier(simulation, "dexterity")), "status": "active", "status_effects": []}}
    for companion in _companions(simulation):
        npc_id = _s(companion.get("npc_id"))
        maximum = int(companion.get("max_hp") or 16)
        calling = _calling_numbers(_d(_d(_d(_sections.world_model_of(simulation)).get("npcs")).get(npc_id)))
        participants[npc_id] = {
            "actor_id": npc_id, "side": "party", "name": _s(companion.get("name")) or npc_id,
            "hp": int(companion.get("hp") if companion.get("hp") is not None else maximum), "max_hp": maximum,
            "armor": calling["armor"], "defense": calling["defense"], "initiative_bonus": calling["initiative_bonus"],
            "status": "active", "status_effects": []}
        if participants[npc_id]["hp"] <= 0:
            participants[npc_id]["status"] = "defeated"  # a companion still down from before sits this one out
    participants[_s(enemy["actor_id"])] = {**enemy, "status_effects": []}
    encounter_id = f"enc:{_s(enemy.get('definition_id'))}:{turn_key}"
    order = build_initiative_order(encounter_id=encounter_id, participants=participants)
    if _s(enemy.get("behaviour")) == "ambushes":  # it strikes first in the first round
        order.sort(key=lambda row: _s(_d(row).get("actor_id")) != _s(enemy["actor_id"]))
    elif confronted:  # it has not struck: the hero chooses first (fight, break away, slip past, talk)
        order.sort(key=lambda row: _s(_d(row).get("actor_id")) != "player")
    return {"active": True, "encounter_id": encounter_id, "round": 1, "turn_index": 0,
            "current_actor_id": _s(_d(order[0]).get("actor_id")) if order else "player",
            "initiative_order": order, "participants": participants, "combat_log": [], "source": SOURCE}


# -- the blows ----------------------------------------------------------------------------------------------------------
def _penalty(conditions: Mapping[str, list[dict[str, Any]]], actor_id: str) -> int:
    return sum(int(row.get("attack_penalty") or 0) for row in conditions.get(actor_id, ()))


def _strike(simulation: Mapping[str, Any], combat: dict[str, Any], conditions: dict[str, list[dict[str, Any]]],
            actor_id: str, target_id: str, *, kind: str = "attack", disadvantage: bool = False,
            cover: int = 0, sharper: int = 0, harder: int = 0) -> dict[str, Any]:
    """One blow, applied to the combat section (and a heavy one's wound to ``conditions``); an ability's blow is
    ``sharper`` (to hit) and ``harder`` (its damage)."""
    numbers = _numbers(simulation, combat, actor_id)
    numbers = {**numbers, "accuracy_bonus": numbers["accuracy_bonus"] + sharper,
               "damage_min": numbers["damage_min"] + harder, "damage_max": numbers["damage_max"] + harder}
    target = participant(combat, target_id)
    roll = deterministic_roll(combat_seed(combat, kind, actor_id, target_id), 1, 20)
    if disadvantage:
        roll = min(roll, deterministic_roll(combat_seed(combat, kind, actor_id, target_id, 2), 1, 20))
    penalty = _penalty(conditions, actor_id)
    total = roll + numbers["accuracy_bonus"] - numbers["encumbrance_penalty"] - penalty
    defense = int(target.get("defense") or 10) + max(0, cover) + (GUARD_BONUS if target.get("guarding") else 0)
    hit = total >= defense
    before = int(target.get("hp") or 0)
    damage = 0
    if hit:
        rolled = deterministic_roll(combat_seed(combat, "damage" if kind == "attack" else f"{kind}:damage", actor_id,
                                                target_id), numbers["damage_min"], numbers["damage_max"])
        damage = max(1, rolled - max(0, int(target.get("armor") or 0)))
    after = max(0, before - damage)
    target["hp"] = after
    if after <= 0:
        target["status"] = "defeated"
    blow = {"actor_id": actor_id, "target_id": target_id, "hit": hit, "attack_roll": roll, "attack_total": total,
            "condition_penalty": penalty, "target_defense": defense, "damage_applied": damage,
            "target_hp_before": before, "target_hp_after": after, "defeated": after <= 0}
    if (hit and after > 0 and _s(target.get("side")) == "party"
            and damage > max(1, int(target.get("max_hp") or 20)) * WOUNDING_SHARE):
        rows = conditions.setdefault(target_id, [])
        if not any(row.get("kind") == WOUNDED for row in rows):
            rows.append({"kind": WOUNDED, "attack_penalty": WOUNDED_PENALTY, "healing_share": 0.5,
                         "rests_left": WOUND_RESTS, "until": "healed", "source": "heavy_blow", "actor_id": target_id})
        blow["wounded"] = True
    combat.setdefault("combat_log", []).append({"kind": kind, "round": int(combat.get("round") or 1), **blow})
    return blow


def _advance(combat: dict[str, Any]) -> None:
    combat.update(next_turn(combat))  # the turn order, the round, and start-of-turn conditions, on the section alone


def _behaves(simulation: Mapping[str, Any], combat: dict[str, Any], actor_id: str) -> dict[str, Any] | None:
    """A creature acting as its kind does on its turn instead of striking (encounters.md): trying once to flee when
    badly hurt (the hero's own rule to break away), or calling an ally once; ``None`` when it simply fights."""
    actor = participant(combat, actor_id)
    behaviour = _s(actor.get("behaviour"))
    hp, most = int(actor.get("hp") or 0), max(1, int(actor.get("max_hp") or 1))
    entry: dict[str, Any] | None = None
    if behaviour == "flees_when_hurt" and hp < most * FLEE_SHARE and not actor.get("tried_to_flee"):
        actor["tried_to_flee"] = True
        roll = deterministic_roll(combat_seed(combat, "flee", actor_id), 1, 20)
        bar = 10 + 2 * max([int(participant(combat, ally).get("initiative_bonus") or 0)
                            for ally in living_party_ids(combat)] or [0])
        escaped = roll + int(actor.get("initiative_bonus") or 0) >= bar
        if escaped:
            actor["status"] = "fled"
        entry = {"kind": "foe_flee", "actor_id": actor_id, "roll": roll, "needed": bar, "escaped": escaped}
    elif behaviour == "calls_allies" and hp < most * CALL_SHARE and not actor.get("called"):
        actor["called"] = True
        entry = {"kind": "foe_call", "actor_id": actor_id,
                 "answered": deterministic_roll(combat_seed(combat, "call", actor_id), 1, 100) <= CALL_CHANCE}
        kin = sum(1 for row in _d(combat.get("participants")).values()
                  if _s(_d(row).get("definition_id")) == _s(actor.get("definition_id")))
        ally = instantiate_campaign_creature(simulation, _s(actor.get("definition_id")), instance_index=kin + 1)
        if entry["answered"] and ally is not None:
            ally_id = _s(ally["actor_id"])
            combat["participants"][ally_id] = {**ally, "called": True, "status_effects": []}  # the ally calls no one
            order = _l(combat.get("initiative_order"))
            order.insert(int(combat.get("turn_index") or 0) + 1, {"actor_id": ally_id, "initiative": 0, "roll": 0,
                                                                   "bonus": 0})
            combat["initiative_order"] = order
            entry["ally_id"] = ally_id
    if entry is not None:
        combat.setdefault("combat_log", []).append({"round": int(combat.get("round") or 1), **entry})
    return entry


def _settle(combat: dict[str, Any]) -> str:
    """Whether the fight is over: '' while both sides stand; the foes gone without one falling is no victory."""
    if not living_enemy_ids(combat):
        if not any(_s(_d(row).get("side")) == "enemy" and int(_d(row).get("hp") or 0) <= 0
                   for row in _d(combat.get("participants")).values()):
            combat.update(active=False, ended_reason="enemy_fled")
            return "foe_fled"
        combat.update(active=False, ended_reason="enemy_side_defeated")
        return "victory"
    if not living_party_ids(combat):
        combat.update(active=False, ended_reason="party_side_defeated")
        return "defeat"
    return ""


def _until_hero(simulation: Mapping[str, Any], combat: dict[str, Any], conditions: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], str]:
    """Everyone whose turn comes before the hero's acts, each striking the first foe standing."""
    blows: list[dict[str, Any]] = []
    for _ in range(2 * max(1, len(_l(combat.get("initiative_order"))))):
        actor_id = current_actor_id(combat)
        if combat.get("active") is not True or not actor_id or actor_id == "player":
            return blows, ""
        actor = participant(combat, actor_id)
        stunned = _s(combat.pop("pending_skip_turn_actor_id", "")) == actor_id
        standing = _s(actor.get("status") or "active") == "active" and int(actor.get("hp") or 0) > 0
        target_id = default_target_for_actor(combat, actor_id)
        if standing and not stunned and target_id:
            acted = _behaves(simulation, combat, actor_id) if _s(actor.get("side")) == "enemy" else None
            blows.append(acted or _strike(simulation, combat, conditions, actor_id, target_id))
            ended = _settle(combat)
            if ended:
                return blows, ended
        hindered = _d(actor.get("hindered"))
        if hindered:  # an ability's hindrance wears off with the turns it lasts
            left = int(hindered.get("turns") or 0) - 1
            if left > 0:
                actor["hindered"] = {**hindered, "turns": left}
            else:
                actor.pop("hindered", None)
        _advance(combat)
    return blows, ""


def _party_as_it_stands(simulation: Mapping[str, Any], combat: dict[str, Any]) -> dict[str, Any]:
    """The party's health is the party's: what healed or hurt them between blows (a potion) holds in the fight."""
    hero = participant(combat, "player")
    if hero:
        hero["hp"] = min(int(hero.get("max_hp") or 0) or _hero_hp(simulation)[1], _hero_hp(simulation)[0])
    for companion in _companions(simulation):
        row = participant(combat, _s(companion.get("npc_id")))
        if row and companion.get("hp") is not None:
            row["hp"] = min(int(row.get("max_hp") or companion["hp"]), int(companion["hp"]))
    return combat


def _named(combat: Mapping[str, Any], target_ref: str) -> str:
    wanted = target_ref.casefold().removeprefix("the ").strip()
    for actor_id in living_enemy_ids(dict(combat)):
        row = participant(dict(combat), actor_id)
        name = _s(row.get("name")).casefold()
        if wanted and (name in wanted or wanted in name or wanted in {actor_id.casefold(), _s(row.get("definition_id")).casefold()}):
            return actor_id
    return ""


# -- the end ------------------------------------------------------------------------------------------------------------
def _spoils(simulation: Mapping[str, Any], combat: Mapping[str, Any]) -> tuple[list[StateChange], list[str]]:
    """What a won fight earns: each fallen creature's experience, and its drops on their seeded chances."""
    # A person beaten yields: no experience or spoils for beating people (combat.md).
    fallen = [participant(dict(combat), actor_id) for actor_id, row in _d(combat.get("participants")).items()
              if _s(_d(row).get("side")) == "enemy" and _s(_d(row).get("kind")) != "person"
              and int(_d(row).get("hp") or 0) <= 0]  # one that got away earns nothing
    # Each creature's experience as the world rates it, or 25 a level where it gives none (combat.md).
    amount = sum(int(row.get("xp_value") or 0) or 25 * max(1, int(row.get("level") or 1)) for row in fallen)
    changes, lines = progression.gain(simulation, amount)  # the one curve, and the level's choice (progression.md)
    items = {_s(row.get("id")): row for row in _l(_d(_sections.world_model_of(simulation)).get("items")) if _s(_d(row).get("id"))}
    for row in fallen:
        definition = campaign_creature_definition(simulation, _s(row.get("definition_id"))) or {}
        for index, drop in enumerate(_l(definition.get("loot"))):
            drop = _d(drop)
            item_id = _s(drop.get("item_id"))
            chance = float(drop.get("chance") or 0)
            roll = deterministic_roll(f"{_s(combat.get('encounter_id'))}|loot|{_s(row.get('actor_id'))}|{index}", 1, 10_000)
            if not item_id or roll > chance * 10_000:
                continue
            item = _d(items.get(item_id))
            name = _s(item.get("name")) or item_id
            quantity = max(1, int(drop.get("quantity") or 1))
            changes.append(ItemAdded(item_id=item_id, name=name, quantity=quantity, category=_s(item.get("type")) or "misc",
                                     fields={"description": _s(item.get("effect")), "rarity": _s(item.get("rarity")),
                                             "source": "loot"}))
            lines.append(f"You take {name}{f' x{quantity}' if quantity > 1 else ''} from {_s(row.get('name')) or 'the fallen'}.")
    return changes, lines


def _copper(purse: Any) -> int:
    purse = _d(purse)
    return int(purse.get("gold") or 0) * 100 + int(purse.get("silver") or 0) * 10 + int(purse.get("copper") or 0)


def _defeat(simulation: Mapping[str, Any], combat: dict[str, Any], conditions: dict[str, list[dict[str, Any]]],
            ) -> tuple[list[StateChange], int]:
    """A lost fight (stakes.md): a setback the hero wakes to, or in hardcore the end. Records it on the section."""
    player = _player(simulation)
    foes = [_s(_d(row).get("name")) for row in _d(combat.get("participants")).values()
            if _s(_d(row).get("side")) == "enemy" and _s(_d(row).get("name"))]
    defeats = int(player.get("defeats") or 0) + 1
    changes: list[StateChange] = [DefeatRecorded(defeats=defeats)]
    if is_hardcore(dict(simulation)):
        combat["defeat"] = {"hardcore": True, "ended": True, "defeated_by": foes[:1]}
        return [*changes, CampaignEnded(reason="defeated", defeated_by=tuple(foes[:1]))], 0
    hero = participant(combat, "player")
    max_hp = max(1, int(hero.get("max_hp") or 20))
    hp = max(1, int(max_hp * DEFEAT_HP_SHARE))
    hero.update(hp=hp, status="active")
    battered: list[str] = []
    for actor_id, rows in conditions.items():
        if not any(row.get("kind") == BATTERED for row in rows):
            rows.append({"kind": BATTERED, "attack_penalty": BATTERED_PENALTY, "check_penalty": BATTERED_PENALTY,
                         "until": "full_rest", "source": "defeat", "actor_id": actor_id})
        battered.append(actor_id)
    store = _d(_sections.inventory_state_of(player))
    total = _copper(store.get("currency") or player.get("currency"))
    lost = max(1, int(total * DEFEAT_PURSE_SHARE)) if total > 0 else 0
    if lost:
        changes.append(PurseChanged(delta_copper=-lost, reason="defeat"))
    item_lost: dict[str, str] = {}
    if deterministic_rng("defeat.item_loss", defeats - 1).random() < DEFEAT_ITEM_LOSS_CHANCE:
        worn = {_s(item_id) for item_id in _d(store.get("equipment")).values() if _s(item_id)}
        carried = [_d(item) for item in _l(store.get("items")) if _d(item)]
        losable = [item for item in carried if _s(item.get("item_id") or item.get("id")) not in worn
                   and item.get("equipped") is not True and item.get("quest_item") is not True
                   and _s(item.get("category")).casefold() != "quest"
                   and "quest" not in {_s(tag).casefold() for tag in _l(item.get("tags"))}]
        if losable:
            pick = max(losable, key=lambda item: (int(item.get("value") or item.get("price") or 0) if not isinstance(
                item.get("value"), dict) else 0, _s(item.get("name"))))
            item_id = _s(pick.get("item_id") or pick.get("id"))
            changes.append(ItemRemoved(item_id=item_id, quantity=1))
            item_lost = {"item_id": item_id, "name": _s(pick.get("name")) or item_id}
    world = _d(_sections.world_model_of(simulation))
    places = _d(world.get("locations"))
    here = _s(player.get("location_id") or simulation.get("location_id"))
    woke_at = next((place for place in (_s(player.get("rest_point")), _s(world.get("start_location_id")), here)
                    if place and place in places), here)
    if woke_at and woke_at != here and woke_at in places:
        place = _d(places[woke_at])
        changes.append(LocationChanged(location_id=woke_at, location_name=_s(place.get("name"))))
        now = routines.clock(simulation)  # who is there as the hero wakes, the hours they were out gone by
        changes.append(PresenceChanged(location_id=woke_at, present_npc_ids=tuple(
            routines.present_at(simulation, woke_at, now + DEFEAT_HOURS * 60, since=now))))
    combat["defeat"] = {"hardcore": False, "defeated_by": foes[:1], "hp": hp, "max_hp": max_hp,
                        "coin_lost_copper": lost, "item_lost": item_lost, "woke_at": woke_at,
                        "woke_at_name": _s(_d(places.get(woke_at)).get("name")) or woke_at, "hours": DEFEAT_HOURS,
                        "battered": battered}
    combat["revived"] = {"actor_id": "player", "hp": hp, "max_hp": max_hp}
    return changes, DEFEAT_HOURS * 60


def _blooded(combat: Mapping[str, Any]) -> bool:
    """Whether blows have been traded."""
    return any(_s(_d(row).get("kind")) in {"attack", "parting_blow"} for row in _l(combat.get("combat_log")))


def _speaks(row: Mapping[str, Any]) -> bool:
    return _s(row.get("kind")) == "person" or row.get("speaks") is True


def _avoid(simulation: Mapping[str, Any], combat: dict[str, Any], *, kind: str, turn_key: str
           ) -> tuple[list[StateChange], list[str], str] | None:
    """Slipping past (a sneak against the foes' best defence, less 2) or talking them down (persuading or
    intimidating, hard): the check's changes and lines, and how the encounter ends ("" when it goes on); ``None``
    when a foe will not be talked to."""
    from app.apps.rpg.rules.checks import DIFFICULTIES, check

    foes = [participant(combat, actor_id) for actor_id in living_enemy_ids(combat)]
    if kind != "sneak" and not all(_speaks(row) for row in foes):
        return None
    lead = foes[0]
    target = _s(lead.get("npc_id")) if _s(lead.get("kind")) == "person" else _s(lead.get("definition_id"))
    difficulty = (max(DIFFICULTIES["trivial"], max(int(row.get("defense") or 10) for row in foes) - 2)
                  if kind == "sneak" else DIFFICULTIES[PARLEY_DIFFICULTY])
    tried = check(simulation, kind, target, turn_key=turn_key, difficulty=difficulty)
    if tried.band == "failure":
        return tried.changes, tried.lines, ""
    ended = "evaded" if kind == "sneak" else "talked_down"
    combat.update(active=False, ended_reason=ended)
    return tried.changes, tried.lines, ended


# -- the turn -----------------------------------------------------------------------------------------------------------
def _defeats(step: Any) -> list[str]:
    """The creatures a quest step names to defeat, however its conditions nest."""
    if isinstance(step, Mapping):
        return [_s(step["defeat"])] if step.get("defeat") else [ref for value in step.values() for ref in _defeats(value)]
    if isinstance(step, (list, tuple)):
        return [ref for value in step for ref in _defeats(value)]
    return []


def _met_here(simulation: Mapping[str, Any], enemy: Mapping[str, Any]) -> bool:
    """Whether the creature can be met where the hero is (encounters.md): in the wild, where no one lives, or at the
    place a quest the hero has taken sends them to defeat it (an inn's cellar rats)."""
    if routines.is_wild(simulation):
        return True
    here = routines.hero_location(simulation)
    kind = _s(enemy.get("definition_id"))
    for quest in _l(_d(_sections.quest_state_of(simulation)).get("quests")):
        quest = _d(quest)
        if quest.get("status") != "active" or here not in {_s(place) for place in _l(quest.get("locations"))}:
            continue
        if any(_s(_d(campaign_creature_definition(simulation, ref)).get("definition_id")) == kind
               for ref in _defeats(quest.get("steps"))):
            return True
    return False


def fight(simulation: Mapping[str, Any], *, action: Action, target_ref: str = "", turn_key: str = "",
          cover: int = 0, ability: FightEffect | None = None, ability_name: str = "",
          parley: Literal["persuade", "intimidate"] = "persuade") -> FightTurn | None:
    """One turn of a fight; ``None`` when the target is neither a creature the world knows nor a person present
    (the older path's).

    ``cover`` is what the target's cover adds to its defence against the hero's blow (the grid's, combat.md);
    ``parley`` is how the hero talks a foe down."""
    existing = _d(_sections.combat_state_of(simulation))
    fighting = existing.get("active") is True
    conditions = _conditions(simulation)
    report: dict[str, Any] = {"earlier_turns": [], "other_turns": [], "parting_blows": [], "foe_ids": []}
    regard: list[StateChange] = []
    if fighting and action in {"sneak", "parley"} and _blooded(existing):
        return FightTurn([], ["Blows have been traded: there is no slipping away or talking now. Strike, break away, "
                              "or use something you carry."], refused=True, minutes=0)
    if not fighting:
        if action in {"flee", "defend", "sneak", "parley"}:
            return FightTurn([], [f"There is no fight to {'flee from' if action == 'flee' else 'guard against'}."],
                             refused=True, minutes=0)
        enemy = instantiate_campaign_creature(simulation, target_ref)
        if enemy is not None and not _met_here(simulation, enemy):  # a wolf is met on the road, not in the guild hall
            return FightTurn([], [f"No {enemy['name']} is here. The world's creatures keep to the wild, where no one "
                                  "lives."], refused=True, minutes=0)
        if enemy is None:
            npc_id, person = _person(simulation, target_ref)
            if not npc_id:
                absent = _known_person(simulation, target_ref)
                if absent:  # someone the world knows, elsewhere at this hour: no blow, and no time passes
                    return FightTurn([], [f"{absent} is not here."], refused=True, minutes=0)
                return None
            name = _s(person.get("name")) or npc_id
            if npc_id in {_s(row.get("npc_id")) for row in _companions(simulation)}:
                return FightTurn([], [f"You will not turn on {name}."], refused=True, minutes=0)
            enemy = _person_foe(npc_id, person)
            people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
            regard = [RegardChanged(npc_id=npc_id, name=name, delta=ATTACKED_REGARD, reason="attacked")]
            regard += [RegardChanged(npc_id=other, name=_s(_d(people.get(other)).get("name")) or other,
                                     delta=WITNESS_REGARD, reason="saw_an_attack")
                       for other in routines.present_now(simulation)[1]
                       if other != npc_id and other in people and other not in {
                           _s(row.get("npc_id")) for row in _companions(simulation)}]
        combat = _start(simulation, enemy, turn_key=turn_key, confronted=action == "confront")
        report["reason"] = "combat_started"
    else:
        combat = _party_as_it_stands(simulation, deepcopy(existing))
    earlier, ended = _until_hero(simulation, combat, conditions)
    report["earlier_turns"] = earlier
    participant(combat, "player").pop("guarding", None)  # a raised guard lasts until the hero's next turn
    tried: list[StateChange] = []
    tried_lines: list[str] = []
    if action == "confront":
        report["reason"] = "combat_confronted"  # the hero's turn is next: fight, break away, slip past, talk
    elif not ended and action in {"sneak", "parley"}:
        avoided = _avoid(simulation, combat, kind="sneak" if action == "sneak" else parley, turn_key=turn_key)
        if avoided is None:
            foe = _s(participant(combat, living_enemy_ids(combat)[0]).get("name")) or "your foe"
            return FightTurn([], [f"The {foe} will not be talked to."], refused=True, minutes=0)
        tried, tried_lines, ended = avoided
        report["reason"] = f"combat_{ended or action + '_failed'}"
        if not ended:
            _advance(combat)  # the try was the hero's turn
    elif not ended and action == "pass":
        _advance(combat)
    elif not ended and action == "defend":
        participant(combat, "player")["guarding"] = True
        report["reason"] = "combat_defended"
        _advance(combat)
    elif not ended and action == "ability":
        effect = ability or FightEffect()
        target_id = _named(combat, target_ref) or default_target_for_actor(combat, "player")
        report.update(ability=ability_name, opening=report.get("reason") == "combat_started")
        if effect.heal:
            hero = participant(combat, "player")
            before = int(hero.get("hp") or 0)
            hero["hp"] = min(int(hero.get("max_hp") or before), before + effect.heal)
            report["healed"] = int(hero["hp"]) - before
        if effect.hinder and target_id:
            participant(combat, target_id)["hindered"] = {"accuracy": effect.hinder, "turns": effect.hinder_turns}
            report["hindered_id"] = target_id
        if effect.strikes and target_id:
            report.update(_strike(simulation, combat, conditions, "player", target_id, cover=cover,
                                  sharper=effect.accuracy_bonus, harder=effect.damage_bonus))
        report["reason"] = "combat_ability"
        ended = _settle(combat)
        if not ended:
            _advance(combat)
    elif not ended and action == "attack":
        target_id = _named(combat, target_ref) or default_target_for_actor(combat, "player")
        blow = _strike(simulation, combat, conditions, "player", target_id, cover=cover)
        report.update(blow, reason=report.get("reason") or ("combat_defeat_resolved" if blow["defeated"]
                                                            else "combat_attack_resolved"))
        ended = _settle(combat)
        if not ended:
            _advance(combat)
    elif not ended:  # breaking away (combat.md)
        hero = participant(combat, "player")
        foe_ids = living_enemy_ids(combat)
        roll = deterministic_roll(combat_seed(combat, "flee", "player"), 1, 20)
        total = roll + int(hero.get("initiative_bonus") or 0)
        bar = 10 + 2 * max([int(participant(combat, foe).get("initiative_bonus") or 0) for foe in foe_ids] or [0])
        # Guardians never leave their post: from them the hero walks away, unpursued (encounters.md).
        unpursued = bool(foe_ids) and all(_s(participant(combat, foe).get("behaviour")) == "guards" for foe in foe_ids)
        escaped = unpursued or total >= bar
        combat.setdefault("combat_log", []).append({"kind": "flee", "round": int(combat.get("round") or 1),
                                                    "actor_id": "player", "roll": roll, "total": total,
                                                    "needed": bar, "escaped": escaped})
        report.update(reason="combat_fled" if escaped else "combat_flee_failed", escaped=escaped, foe_ids=foe_ids)
        if escaped:
            for foe_id in [] if unpursued else foe_ids:
                if int(participant(combat, "player").get("hp") or 0) <= 0:
                    break
                report["parting_blows"].append({**_strike(simulation, combat, conditions, foe_id, "player",
                                                          kind="parting_blow", disadvantage=True), "parting_blow": True})
            ended = _settle(combat) if not living_party_ids(combat) else "fled"
            if ended == "fled":
                combat.update(active=False, ended_reason="party_fled")
        else:
            _advance(combat)
    if not ended:
        later, ended = _until_hero(simulation, combat, conditions)
        report["other_turns"] = later
    changes: list[StateChange] = []
    minutes = MINUTES_PER_TURN
    spoils: list[str] = []
    after: list[StateChange] = []
    if ended == "victory":
        after, spoils = _spoils(simulation, combat)
        # Fought beside them and won (the playtest: a whole campaign together, and Liora's regard moved only when a
        # quest ended).
        after = [*after, *(RegardChanged(npc_id=_s(row.get("npc_id")), name=_s(row.get("name")) or _s(row.get("npc_id")),
                                         delta=FOUGHT_BESIDE_REGARD, reason="fought_beside")
                           for row in _companions(simulation)
                           if int(participant(combat, _s(row.get("npc_id"))).get("hp") or 0) > 0)]
    elif ended == "defeat":
        after, minutes = _defeat(simulation, combat, conditions)
        minutes = minutes or MINUTES_PER_TURN
    changes.append(CombatAdvanced(combat_state=combat))
    start_hp, _ = _hero_hp(simulation)
    hero_hp = int(participant(combat, "player").get("hp") or 0)
    if hero_hp != start_hp:
        changes.append(HpChanged(delta=hero_hp - start_hp))
    for companion in _companions(simulation):
        npc_id = _s(companion.get("npc_id"))
        row = participant(combat, npc_id)
        if row and int(row.get("hp") or 0) != int(companion.get("hp") if companion.get("hp") is not None else row.get("max_hp") or 0):
            changes.append(CompanionHpChanged(npc_id=npc_id, hp=max(0, int(row.get("hp") or 0))))
    before = _conditions(simulation)
    changes.extend(ConditionsChanged(actor_id=actor_id, conditions=tuple(rows))
                   for actor_id, rows in conditions.items() if rows != before.get(actor_id, []))
    changes.extend(after)
    changes.extend(regard)
    changes.extend(tried)
    report["combat_state"] = combat
    if action == "pass" and report.get("reason") is None:
        report["reason"] = "combat_turn_passed"
    lines = [*tried_lines, *describe_combat_exchange(report), *spoils]
    return FightTurn(changes, lines, minutes=minutes, ended=ended, report=report)


__all__ = ["ATTACKED_REGARD", "FOUGHT_BESIDE_REGARD", "FightTurn", "GUARD_BONUS", "MINUTES_PER_TURN", "WITNESS_REGARD", "fight"]
