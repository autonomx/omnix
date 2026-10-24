"""A fight, as the turn pipeline plays it (RQ-2.6; docs/rpg/design/combat.md): one pure rule, from the campaign
to the changes.

``fight`` reads the campaign (never writes it) and returns what one turn of a fight does: the combat section as the
turn leaves it, the party's health and wounds, and at the end what the fight earned (the creatures' experience and
drops, from the world's bestiary) or cost (the setback of a lost fight, stakes.md). The blows are seeded, so the same
campaign and command fight the same way.
"""
from __future__ import annotations

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
    ExperienceGained,
    HpChanged,
    ItemAdded,
    ItemRemoved,
    LevelReached,
    LocationChanged,
    PresenceChanged,
    PurseChanged,
    StateChange,
)
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
from app.apps.rpg.rules.combat.runtime_turns import advance_combat_turn
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

SOURCE = "rpg_turn_pipeline_fight_v1"
MINUTES_PER_TURN = 1
Action = Literal["attack", "flee", "pass"]  # pass: the hero's turn went on something else (a potion)


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
    return _d(simulation.get("player_state"))


def _hero_hp(simulation: Mapping[str, Any]) -> tuple[int, int]:
    player = _player(simulation)
    pool = _d(_d(player.get("resources")).get("hp"))
    maximum = int(pool.get("max") or player.get("max_hp") or 20)
    return int(pool.get("current") if pool.get("current") is not None else player.get("hp") or maximum), maximum


def _companions(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(row) for row in _l(_d(_player(simulation).get("party_state")).get("companions")) if _s(_d(row).get("npc_id"))]


def _conditions(simulation: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Each party member's lingering conditions, as stored (copies the fight may add to)."""
    party = {"player": [_d(row) for row in _l(_player(simulation).get("conditions")) if _d(row)]}
    for companion in _companions(simulation):
        party[_s(companion.get("npc_id"))] = [_d(row) for row in _l(companion.get("conditions")) if _d(row)]
    return deepcopy(party)


def _numbers(simulation: Mapping[str, Any], combat: Mapping[str, Any], actor_id: str) -> dict[str, int]:
    row = participant(dict(combat), actor_id)
    if _s(row.get("side")) == "enemy":
        return {"damage_min": max(1, int(row.get("damage_min") or 1)), "damage_max": max(1, int(row.get("damage_max") or 3)),
                "accuracy_bonus": int(row.get("accuracy_bonus") or 0), "encumbrance_penalty": 0}
    stats = _d(project_equipment_stats(dict(simulation), actor_id=actor_id).get("stats"))
    return {"damage_min": max(1, int(stats.get("damage_min") or 1)), "damage_max": max(1, int(stats.get("damage_max") or 2)),
            "accuracy_bonus": int(stats.get("accuracy_bonus") or 0),
            "encumbrance_penalty": int(stats.get("encumbrance_penalty") or 0)}


def _start(simulation: Mapping[str, Any], enemy: dict[str, Any], *, turn_key: str) -> dict[str, Any]:
    hp, max_hp = _hero_hp(simulation)
    armor = int(_d(project_equipment_stats(dict(simulation), actor_id="player").get("stats")).get("armor") or 0)
    participants: dict[str, dict[str, Any]] = {"player": {
        "actor_id": "player", "side": "party", "name": "You", "hp": hp, "max_hp": max_hp, "armor": armor,
        "defense": 10, "initiative_bonus": 1, "status": "active", "status_effects": []}}
    for companion in _companions(simulation):
        npc_id = _s(companion.get("npc_id"))
        maximum = int(companion.get("max_hp") or 16)
        participants[npc_id] = {
            "actor_id": npc_id, "side": "party", "name": _s(companion.get("name")) or npc_id,
            "hp": int(companion.get("hp") if companion.get("hp") is not None else maximum), "max_hp": maximum,
            "armor": 0, "defense": 10, "initiative_bonus": 0, "status": "active", "status_effects": []}
        if participants[npc_id]["hp"] <= 0:
            participants[npc_id]["status"] = "defeated"  # a companion still down from before sits this one out
    participants[_s(enemy["actor_id"])] = {**enemy, "status_effects": []}
    encounter_id = f"enc:{_s(enemy.get('definition_id'))}:{turn_key}"
    order = build_initiative_order(encounter_id=encounter_id, participants=participants)
    return {"active": True, "encounter_id": encounter_id, "round": 1, "turn_index": 0,
            "current_actor_id": _s(_d(order[0]).get("actor_id")) if order else "player",
            "initiative_order": order, "participants": participants, "combat_log": [], "source": SOURCE}


# -- the blows ----------------------------------------------------------------------------------------------------------
def _penalty(conditions: Mapping[str, list[dict[str, Any]]], actor_id: str) -> int:
    return sum(int(row.get("attack_penalty") or 0) for row in conditions.get(actor_id, ()))


def _strike(simulation: Mapping[str, Any], combat: dict[str, Any], conditions: dict[str, list[dict[str, Any]]],
            actor_id: str, target_id: str, *, kind: str = "attack", disadvantage: bool = False) -> dict[str, Any]:
    """One blow, applied to the combat section (and a heavy one's wound to ``conditions``)."""
    numbers = _numbers(simulation, combat, actor_id)
    target = participant(combat, target_id)
    roll = deterministic_roll(combat_seed(combat, kind, actor_id, target_id), 1, 20)
    if disadvantage:
        roll = min(roll, deterministic_roll(combat_seed(combat, kind, actor_id, target_id, 2), 1, 20))
    penalty = _penalty(conditions, actor_id)
    total = roll + numbers["accuracy_bonus"] - numbers["encumbrance_penalty"] - penalty
    defense = int(target.get("defense") or 10)
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
    holder = {"combat_state": combat}
    advance_combat_turn(holder)  # the turn order, the round, and start-of-turn conditions, on the section alone
    combat.update(holder["combat_state"])


def _settle(combat: dict[str, Any]) -> str:
    """Whether the fight is over: '' while both sides stand."""
    if not living_enemy_ids(combat):
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
            blows.append(_strike(simulation, combat, conditions, actor_id, target_id))
            ended = _settle(combat)
            if ended:
                return blows, ended
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
    fallen = [participant(dict(combat), actor_id) for actor_id, row in _d(combat.get("participants")).items()
              if _s(_d(row).get("side")) == "enemy"]
    # Each creature's experience as the world rates it, or 25 a level where it gives none (combat.md).
    amount = sum(int(row.get("xp_value") or 0) or 25 * max(1, int(row.get("level") or 1)) for row in fallen)
    changes: list[StateChange] = []
    lines: list[str] = []
    if amount:
        changes.append(ExperienceGained(amount=amount))
        lines.append(f"You gain {amount} experience.")
        player = _player(simulation)
        level = int(player.get("level") or 1)
        xp = int(player.get("xp") or 0) + amount
        to_next = int(player.get("xp_to_next") or 100)
        points, skill_points = int(player.get("unspent_points") or 0), int(player.get("unspent_skill_points") or 0)
        rose = False
        while xp >= to_next:  # the hero's curve (rules/player/player_progression_state.py)
            xp -= to_next
            level, points, skill_points, rose = level + 1, points + 2, skill_points + 1, True
            to_next = level * 100
        if rose:
            changes.append(LevelReached(level=level, xp=xp, xp_to_next=to_next, unspent_points=points,
                                        unspent_skill_points=skill_points))
            lines.append(f"You reach level {level}.")
    items = {_s(row.get("id")): row for row in _l(_d(simulation.get("world_model")).get("items")) if _s(_d(row).get("id"))}
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
    store = _d(player.get("inventory_state"))
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
    world = _d(simulation.get("world_model"))
    places = _d(world.get("locations"))
    here = _s(player.get("location_id") or simulation.get("location_id"))
    woke_at = next((place for place in (_s(player.get("rest_point")), _s(world.get("start_location_id")), here)
                    if place and place in places), here)
    if woke_at and woke_at != here and woke_at in places:
        place = _d(places[woke_at])
        changes.append(LocationChanged(location_id=woke_at, location_name=_s(place.get("name"))))
        changes.append(PresenceChanged(location_id=woke_at, present_npc_ids=tuple(
            _s(_d(npc).get("id")) for npc in _l(place.get("present_npcs")) if _s(_d(npc).get("id")))))
    combat["defeat"] = {"hardcore": False, "defeated_by": foes[:1], "hp": hp, "max_hp": max_hp,
                        "coin_lost_copper": lost, "item_lost": item_lost, "woke_at": woke_at,
                        "woke_at_name": _s(_d(places.get(woke_at)).get("name")) or woke_at, "hours": DEFEAT_HOURS,
                        "battered": battered}
    combat["revived"] = {"actor_id": "player", "hp": hp, "max_hp": max_hp}
    return changes, DEFEAT_HOURS * 60


# -- the turn -----------------------------------------------------------------------------------------------------------
def fight(simulation: Mapping[str, Any], *, action: Action, target_ref: str = "", turn_key: str = "") -> FightTurn | None:
    """One turn of a fight; ``None`` when the target is not a creature the world knows (the older path's)."""
    existing = _d(simulation.get("combat_state"))
    fighting = existing.get("active") is True
    conditions = _conditions(simulation)
    report: dict[str, Any] = {"earlier_turns": [], "other_turns": [], "parting_blows": [], "foe_ids": []}
    if not fighting:
        if action == "flee":
            return FightTurn([], ["There is no fight to flee from."], refused=True, minutes=0)
        enemy = instantiate_campaign_creature(simulation, target_ref)
        if enemy is None:
            return None
        combat = _start(simulation, enemy, turn_key=turn_key)
        report["reason"] = "combat_started"
    else:
        combat = _party_as_it_stands(simulation, deepcopy(existing))
    earlier, ended = _until_hero(simulation, combat, conditions)
    report["earlier_turns"] = earlier
    if not ended and action == "pass":
        _advance(combat)
    elif not ended and action == "attack":
        target_id = _named(combat, target_ref) or default_target_for_actor(combat, "player")
        blow = _strike(simulation, combat, conditions, "player", target_id)
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
        escaped = total >= bar
        combat.setdefault("combat_log", []).append({"kind": "flee", "round": int(combat.get("round") or 1),
                                                    "actor_id": "player", "roll": roll, "total": total,
                                                    "needed": bar, "escaped": escaped})
        report.update(reason="combat_fled" if escaped else "combat_flee_failed", escaped=escaped, foe_ids=foe_ids)
        if escaped:
            for foe_id in foe_ids:
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
    report["combat_state"] = combat
    if action == "pass" and report.get("reason") is None:
        report["reason"] = "combat_turn_passed"
    lines = [*describe_combat_exchange(report), *spoils]
    return FightTurn(changes, lines, minutes=minutes, ended=ended, report=report)


__all__ = ["FightTurn", "MINUTES_PER_TURN", "fight"]
