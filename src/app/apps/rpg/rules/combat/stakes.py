"""What a lost fight costs, and what a rest restores (RQ-5.1; docs/rpg/design/stakes.md).

A standard defeat is a setback: the hero wakes where they last rested, hurt and battered, lighter in the
purse, perhaps without something they carried. In a hardcore campaign defeat ends the hero's story. A heavy
blow leaves a wound that lingers until a potion, a healer or two nights' rest.
"""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.core.determinism import deterministic_rng
from app.apps.rpg.foundation.safe_values import safe_dict, safe_list, safe_str
from app.apps.rpg.rules.combat.runtime_core import participant, safe_int, sync_participant_hp_to_actor_state
from app.apps.rpg.rules.location_registry import default_location_id, get_location, set_current_location

DEFEAT_HOURS = 8
DEFEAT_HP_SHARE = 0.25
DEFEAT_PURSE_SHARE = 0.20
DEFEAT_ITEM_LOSS_CHANCE = 0.5
BATTERED = "battered"
BATTERED_PENALTY = 2
WOUNDED = "wounded"
WOUNDING_SHARE = 0.4  # a blow taking more than this share of max HP in one go wounds
WOUNDED_PENALTY = 1
WOUND_RESTS = 2
FULL_RESTS = frozenset({"sleep", "inn_lodging", "make_camp"})


def is_hardcore(simulation_state: dict[str, Any]) -> bool:
    return safe_dict(simulation_state.get("campaign_rules")).get("hardcore") is True


def campaign_ended(simulation_state: dict[str, Any]) -> dict[str, Any]:
    """How the campaign ended ({} while it goes on)."""
    return safe_dict(simulation_state.get("campaign_end"))


def conditions(actor: dict[str, Any]) -> list[dict[str, Any]]:
    return [safe_dict(condition) for condition in safe_list(safe_dict(actor).get("conditions")) if safe_dict(condition)]


def attack_penalty(simulation_state: dict[str, Any], actor_id: str) -> int:
    """What the actor's lingering conditions take off their attack rolls."""
    actor = _actor(simulation_state, actor_id)
    return sum(safe_int(condition.get("attack_penalty"), 0) for condition in conditions(actor))


def record_rest(simulation_state: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """A full rest (a night's lodging, sleep, a camp) is where a beaten hero wakes; it ends being battered and
    brings a wound a night nearer healing."""
    if kind not in FULL_RESTS:
        return {}
    player = _player(simulation_state)
    location_id = safe_str(player.get("location_id") or simulation_state.get("location_id"))
    if location_id:
        player["rest_point"] = location_id
    healed: list[str] = []
    for actor_id, actor in _party(simulation_state):
        battered = _remove(actor, BATTERED)
        if _rest_wound(actor) or battered:
            healed.append(actor_id)
    return {"rest_point": location_id, "healed": healed}


def wound_on_heavy_blow(simulation_state: dict[str, Any], actor_id: str, *, damage: int, max_hp: int) -> bool:
    """A blow taking more than two fifths of a party member's strength at once leaves them wounded."""
    actor = _actor(simulation_state, actor_id)
    if not actor or damage <= max(1, max_hp) * WOUNDING_SHARE:
        return False
    if not any(condition.get("kind") == WOUNDED for condition in conditions(actor)):
        actor["conditions"] = [*conditions(actor), {"kind": WOUNDED, "attack_penalty": WOUNDED_PENALTY,
                                                     "healing_share": 0.5, "rests_left": WOUND_RESTS,
                                                     "until": "healed", "source": "heavy_blow", "actor_id": actor_id}]
    return True


def healing(simulation_state: dict[str, Any], actor_id: str, amount: int) -> int:
    """How much of a heal takes hold: half while wounded."""
    actor = _actor(simulation_state, actor_id)
    if any(condition.get("kind") == WOUNDED for condition in conditions(actor)):
        return max(0, amount) // 2
    return max(0, amount)


def treat_wound(simulation_state: dict[str, Any], actor_id: str) -> bool:
    """A potion or a healer's care closes a wound."""
    return _remove(_actor(simulation_state, actor_id), WOUNDED)


def apply_defeat(simulation_state: dict[str, Any], combat_state: dict[str, Any]) -> dict[str, Any]:
    """The party fell: the setback the hero wakes to, or in hardcore the end of the campaign.

    Records it as ``combat_state["defeat"]``; the clock moving on (``hours``) is the session's to apply,
    since time is the world's.
    """
    hero = participant(combat_state, "player")
    if not hero:
        return {}
    foes = [safe_str(row.get("name")) for row in safe_dict(combat_state.get("participants")).values()
            if safe_dict(row).get("side") == "enemy" and safe_str(safe_dict(row).get("name"))]
    player = _player(simulation_state)
    player["defeats"] = safe_int(player.get("defeats"), 0) + 1
    if is_hardcore(simulation_state):
        simulation_state["campaign_end"] = {"ended": True, "reason": "defeated", "defeated_by": foes[:1],
                                            "tick": safe_int(simulation_state.get("tick"), 0)}
        defeat = {"hardcore": True, "ended": True, "defeated_by": foes[:1]}
        combat_state["defeat"] = defeat
        return defeat

    max_hp = max(1, safe_int(hero.get("max_hp"), 20))
    hp = max(1, int(max_hp * DEFEAT_HP_SHARE))
    hero["hp"] = hp
    hero["status"] = "active"
    sync_participant_hp_to_actor_state(simulation_state, actor_id="player", hp=hp, status="battered")
    battered = [actor_id for actor_id, actor in _party(simulation_state) if _add_battered(actor, actor_id)]
    coin_lost = _lose_coin(simulation_state)
    item_lost = _lose_item(simulation_state)
    woke_at = _wake_location(simulation_state)
    set_current_location(simulation_state, woke_at)
    defeat = {
        "hardcore": False,
        "defeated_by": foes[:1],
        "hp": hp,
        "max_hp": max_hp,
        "coin_lost_copper": coin_lost,
        "item_lost": item_lost,
        "woke_at": woke_at,
        "woke_at_name": safe_str(get_location(woke_at, simulation_state).get("name")) or woke_at,
        "hours": DEFEAT_HOURS,
        "battered": battered,
    }
    combat_state["defeat"] = defeat
    combat_state["revived"] = {"actor_id": "player", "hp": hp, "max_hp": max_hp}
    return defeat


def _player(simulation_state: dict[str, Any]) -> dict[str, Any]:
    player = simulation_state.get("player_state")
    if not isinstance(player, dict):
        player = simulation_state["player_state"] = {}
    return player


def _party(simulation_state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The hero and the companions with them, as stored (mutable)."""
    player = _player(simulation_state)
    members: list[tuple[str, dict[str, Any]]] = [("player", player)]
    for companion in safe_list(safe_dict(player.get("party_state")).get("companions")):
        if isinstance(companion, dict) and safe_str(companion.get("npc_id")):
            members.append((safe_str(companion.get("npc_id")), companion))
    return members


def _actor(simulation_state: dict[str, Any], actor_id: str) -> dict[str, Any]:
    return next((actor for member_id, actor in _party(simulation_state) if member_id == actor_id), {})


def _add_battered(actor: dict[str, Any], actor_id: str) -> bool:
    if any(condition.get("kind") == BATTERED for condition in conditions(actor)):
        return True
    actor["conditions"] = [*conditions(actor), {"kind": BATTERED, "attack_penalty": BATTERED_PENALTY,
                                                 "check_penalty": BATTERED_PENALTY, "until": "full_rest",
                                                 "source": "defeat", "actor_id": actor_id}]
    return True


def _remove(actor: dict[str, Any], kind: str) -> bool:
    kept = [condition for condition in conditions(actor) if condition.get("kind") != kind]
    removed = len(kept) != len(conditions(actor))
    if removed:
        actor["conditions"] = kept
    return removed


def _rest_wound(actor: dict[str, Any]) -> bool:
    """A night's rest on a wound; True when it closes."""
    kept: list[dict[str, Any]] = []
    closed = False
    for condition in conditions(actor):
        if condition.get("kind") == WOUNDED:
            left = safe_int(condition.get("rests_left"), WOUND_RESTS) - 1
            if left <= 0:
                closed = True
                continue
            condition = {**condition, "rests_left": left}
        kept.append(condition)
    if conditions(actor):
        actor["conditions"] = kept
    return closed


def _copper(purse: Any) -> int:
    purse = safe_dict(purse)
    return safe_int(purse.get("gold"), 0) * 100 + safe_int(purse.get("silver"), 0) * 10 + safe_int(purse.get("copper"), 0)


def _purse(copper: int) -> dict[str, int]:
    return {"gold": copper // 100, "silver": copper // 10 % 10, "copper": copper % 10}


def _lose_coin(simulation_state: dict[str, Any]) -> int:
    """A fifth of the purse, rounded down, at least a copper while there is any (the one purse, RQ-2.0)."""
    player = _player(simulation_state)
    store = player.get("inventory_state") if isinstance(player.get("inventory_state"), dict) else {}
    total = _copper(store.get("currency") or player.get("currency"))
    if total <= 0:
        return 0
    lost = max(1, int(total * DEFEAT_PURSE_SHARE))
    player["currency"] = _purse(total - lost)
    if store:
        store["currency"] = _purse(total - lost)
    return lost


def _lose_item(simulation_state: dict[str, Any]) -> dict[str, Any]:
    """On a seeded even chance, the most valuable thing carried that is neither worn nor wanted by a quest."""
    if deterministic_rng("defeat.item_loss", safe_int(_player(simulation_state).get("defeats"), 0)).random() >= DEFEAT_ITEM_LOSS_CHANCE:
        return {}
    store = safe_dict(_player(simulation_state).get("inventory_state"))
    items = [item for item in safe_list(store.get("items")) if isinstance(item, dict)]
    worn = {safe_str(item_id) for item_id in safe_dict(store.get("equipment")).values() if safe_str(item_id)}
    candidates = [item for item in items if _losable(item, worn)]
    if not candidates:
        return {}
    lost = max(candidates, key=lambda item: (safe_int(item.get("value") or item.get("price"), 0), safe_str(item.get("name"))))
    quantity = safe_int(lost.get("qty") if lost.get("qty") is not None else lost.get("quantity"), 1)
    if quantity > 1:
        lost["qty" if "qty" in lost else "quantity"] = quantity - 1
    else:
        store["items"] = [item for item in items if item is not lost]
    return {"item_id": _item_id(lost), "name": safe_str(lost.get("name")) or _item_id(lost)}


def _item_id(item: dict[str, Any]) -> str:
    return safe_str(item.get("item_id") or item.get("id"))


def _losable(item: dict[str, Any], worn: set[str]) -> bool:
    tags = {safe_str(tag).casefold() for tag in safe_list(item.get("tags"))}
    return not (
        _item_id(item) in worn
        or item.get("equipped") is True
        or item.get("quest_item") is True
        or safe_str(item.get("category")).casefold() == "quest"
        or "quest" in tags
    )


def _wake_location(simulation_state: dict[str, Any]) -> str:
    """The last place the hero rested, or the place the campaign opened."""
    player = _player(simulation_state)
    for location_id in (player.get("rest_point"), default_location_id(simulation_state)):
        if safe_str(location_id) and get_location(safe_str(location_id), simulation_state):
            return safe_str(location_id)
    return safe_str(player.get("location_id") or simulation_state.get("location_id"))


__all__ = [
    "BATTERED",
    "DEFEAT_HOURS",
    "WOUNDED",
    "apply_defeat",
    "attack_penalty",
    "campaign_ended",
    "conditions",
    "healing",
    "is_hardcore",
    "record_rest",
    "treat_wound",
    "wound_on_heavy_blow",
]
