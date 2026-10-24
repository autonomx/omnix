"""A turn's exchange of blows, stated plainly for the narration (the runtime decides; the narrator tells)."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.rules.combat.runtime_core import participant, safe_dict, safe_int, safe_list, safe_str


def _name(combat_state: dict[str, Any], actor_id: str, *, subject: bool) -> str:
    if actor_id == "player":
        return "You" if subject else "you"
    row = participant(combat_state, actor_id)
    name = safe_str(row.get("name")) or "your foe"
    # A creature is one of its kind ("the Echo Wolf"); a companion goes by their own name.
    if safe_str(row.get("side")) == "enemy" and not name.casefold().startswith(("the ", "your ")):
        name = f"the {name}"
    return name[:1].upper() + name[1:] if subject else name


def _blow(combat_state: dict[str, Any], attack: dict[str, Any]) -> str:
    actor_id = safe_str(attack.get("actor_id"))
    target_id = safe_str(attack.get("target_id"))
    actor = _name(combat_state, actor_id, subject=True)
    target = _name(combat_state, target_id, subject=False)
    verb = "hit" if actor_id == "player" else "hits"
    if not attack.get("hit"):
        return f"{actor} {'miss' if actor_id == 'player' else 'misses'} {target}."
    left = safe_int(attack.get("target_hp_after"), 0)
    most = safe_int(participant(combat_state, target_id).get("max_hp"), 0)
    if attack.get("defeated"):
        return f"{actor} {verb} {target} for {safe_int(attack.get('damage_applied'), 0)}, and {target} falls."
    return f"{actor} {verb} {target} for {safe_int(attack.get('damage_applied'), 0)} ({left} of {most} left)."


def _defeat_lines(defeat: dict[str, Any], foes: str) -> list[str]:
    """What a lost fight cost, as facts the narrator may not soften (RQ-5.1)."""
    by = " and ".join(name if name.casefold().startswith(("the ", "your ")) else f"the {name}"
                      for name in map(safe_str, safe_list(defeat.get("defeated_by"))) if name) or foes or "your foe"
    if defeat.get("ended"):
        return [f"You fall to {by}, and do not rise again. Your story ends here."]
    lines = [
        f"You fall to {by}, and the fight is lost. You wake at {safe_str(defeat.get('woke_at_name')) or 'the last place you rested'} "
        f"{safe_int(defeat.get('hours'), 8)} hours later, battered "
        f"({safe_int(defeat.get('hp'), 1)} of {safe_int(defeat.get('max_hp'), 1)} left)."
    ]
    if safe_int(defeat.get("coin_lost_copper"), 0) > 0:
        lines.append(f"Your purse is lighter by {safe_int(defeat.get('coin_lost_copper'), 0)} copper.")
    if safe_dict(defeat.get("item_lost")):
        lines.append(f"Your {safe_str(safe_dict(defeat.get('item_lost')).get('name'))} is gone.")
    return lines


def describe_combat_exchange(combat_result: dict[str, Any]) -> list[str]:
    """The blows struck this turn, in the order they fell, and how the fight stands after them."""
    combat_result = safe_dict(combat_result)
    combat_state = safe_dict(combat_result.get("combat_state"))
    if not combat_state:
        return []
    lines: list[str] = []
    if safe_str(combat_result.get("reason")) == "combat_started":
        foes = [_name(combat_state, safe_str(actor_id), subject=False)
                for actor_id, row in safe_dict(combat_state.get("participants")).items()
                if safe_str(safe_dict(row).get("side")) == "enemy"]
        lines.append(f"The fight begins: you against {' and '.join(foes) or 'your foe'}.")
    reason = safe_str(combat_result.get("reason"))
    foes = " and ".join(_name(combat_state, safe_str(foe), subject=False) for foe in safe_list(combat_result.get("foe_ids")))
    if reason == "combat_fled":
        lines.append(f"You break away from {foes or 'the fight'} and escape; the fight is over.")
    elif reason == "combat_flee_failed":
        lines.append(f"You try to break away, but {foes or 'your foe'} cuts you off.")
    attacks = [
        *safe_list(combat_result.get("earlier_turns")),
        *([combat_result] if combat_result.get("hit") is not None else []),
        *safe_list(combat_result.get("other_turns")),
    ]
    lines.extend(_blow(combat_state, safe_dict(attack)) for attack in attacks)
    ended = safe_str(combat_state.get("ended_reason"))
    if combat_state.get("active") is not True and ended == "enemy_side_defeated":
        lines.append("The fight is over.")
    elif combat_state.get("active") is not True and ended == "party_side_defeated":
        lines.extend(_defeat_lines(safe_dict(combat_state.get("defeat")), foes))
    return lines


__all__ = ["describe_combat_exchange"]
