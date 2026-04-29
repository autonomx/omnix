from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.interactions.consumable_runtime import apply_consumable_interaction
from app.rpg.interactions.container_runtime import apply_container_interaction
from app.rpg.interactions.crafting_runtime import apply_crafting_interaction
from app.rpg.interactions.equipment_runtime import project_equipment_stats
from app.rpg.interactions.inventory_runtime import apply_inventory_interaction
from app.rpg.interactions.merchant_runtime import apply_merchant_interaction
from app.rpg.interactions.repair_runtime import apply_repair_interaction
from app.rpg.interactions.semantic_actions import (
    resolve_semantic_action_v2,
    semantic_action_kind,
)
from app.rpg.interactions.target_resolver import (
    expected_target_types_for_action,
    resolve_target_ref,
)
from app.rpg.combat.runtime import (
    gate_combat_action,
    is_combat_active,
    start_combat_encounter,
)


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_unresolved_result(action: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "resolved": False,
        "changed_state": False,
        "reason": reason,
        "semantic_action_v2": deepcopy(action),
        "source": "deterministic_general_interaction_runtime",
    }


def _interaction_reason_for_kind(kind: str) -> str:
    if kind == "inspect":
        return "target_inspected"
    if kind == "open":
        return "open_requires_world_object_runtime"
    if kind == "close":
        return "close_requires_world_object_runtime"
    if kind == "take":
        return "take_requires_inventory_runtime"
    if kind == "drop":
        return "drop_requires_inventory_runtime"
    if kind == "give":
        return "give_requires_inventory_runtime"
    if kind == "use":
        return "use_requires_item_interaction_runtime"
    if kind == "repair":
        return "repair_requires_item_condition_runtime"
    if kind == "equip":
        return "equip_requires_inventory_runtime"
    if kind == "unequip":
        return "unequip_requires_inventory_runtime"
    if kind == "attack":
        return "attack_requires_combat_runtime"
    if kind == "talk":
        return "talk_handled_by_conversation_runtime"
    return "unsupported_interaction_kind"


def _allowed_sources_for_action(kind: str) -> list[str]:
    if kind == "take":
        return ["scene_items", "location_items", "world_items"]
    if kind in {"drop", "equip", "unequip", "give", "put", "repair", "consume"}:
        return ["player_inventory"]
    return []


def resolve_general_interaction(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    actor_id: str = "player",
    tick: int = 0,
) -> Dict[str, Any]:
    action = resolve_semantic_action_v2(
        player_input=player_input,
        actor_id=actor_id,
    )
    kind = semantic_action_kind(action)

    if not action.get("resolved"):
        return {
            "handled": False,
            "semantic_action_v2": deepcopy(action),
            "interaction_result": _build_unresolved_result(action, _safe_str(action.get("reason"))),
            "source": "deterministic_general_interaction_runtime",
        }

    if kind == "attack":
        enriched_action = deepcopy(action)

        if not is_combat_active(simulation_state):
            combat_result = start_combat_encounter(
                simulation_state,
                encounter_id="enc:bandit_ambush",
                tick=tick,
            )
        else:
            combat_result = gate_combat_action(
                simulation_state,
                actor_id=_safe_str(enriched_action.get("actor_id") or actor_id or "player"),
                action_kind="attack",
            )

        interaction_result = {
            "resolved": bool(combat_result.get("resolved")),
            "changed_state": bool(combat_result.get("changed_state")),
            "reason": _safe_str(combat_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "combat_result": deepcopy(combat_result),
            "combat_state": deepcopy(combat_result.get("combat_state") or simulation_state.get("combat_state") or {}),
            "source": "deterministic_general_interaction_runtime",
        }

        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "combat_result": deepcopy(combat_result),
            "combat_state": deepcopy(interaction_result.get("combat_state")),
            "source": "deterministic_general_interaction_runtime",
        }

    if kind == "craft":
        enriched_action = deepcopy(action)
        crafting_result = apply_crafting_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )
        interaction_result = {
            "resolved": bool(crafting_result.get("resolved")),
            "changed_state": bool(crafting_result.get("changed_state")),
            "reason": _safe_str(crafting_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "crafting_result": deepcopy(crafting_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "crafting_result": deepcopy(crafting_result),
            "source": "deterministic_general_interaction_runtime",
        }

    if kind in {"buy", "sell"}:
        enriched_action = deepcopy(action)
        merchant_result = apply_merchant_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )
        interaction_result = {
            "resolved": bool(merchant_result.get("resolved")),
            "changed_state": bool(merchant_result.get("changed_state")),
            "reason": _safe_str(merchant_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "merchant_result": deepcopy(merchant_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "merchant_result": deepcopy(merchant_result),
            "source": "deterministic_general_interaction_runtime",
        }

    target_ref = _safe_str(action.get("target_ref"))
    expected_types = expected_target_types_for_action(kind)
    target_result = resolve_target_ref(
        simulation_state,
        target_ref=target_ref,
        expected_types=expected_types,
        allowed_sources=_allowed_sources_for_action(kind),
    ) if target_ref else {
        "resolved": False,
        "reason": "missing_target_ref",
        "target_ref": target_ref,
        "source": "deterministic_target_resolver",
    }

    enriched_action = deepcopy(action)
    enriched_action["target_resolution"] = deepcopy(target_result)
    if target_result.get("resolved"):
        enriched_action["target_id"] = _safe_str(target_result.get("target_id"))
        enriched_action["target_type"] = _safe_str(target_result.get("target_type"))

    secondary_result = {}
    secondary_ref = _safe_str(
        action.get("secondary_target_ref")
        or action.get("recipient_ref")
    )
    if secondary_ref:
        secondary_expected = ["npc"] if kind == "give" else []
        secondary_allowed_sources = []
        if kind in {"put", "repair"}:
            secondary_expected = ["item"]
            secondary_allowed_sources = ["player_inventory"]

        secondary_result = resolve_target_ref(
            simulation_state,
            target_ref=secondary_ref,
            expected_types=secondary_expected,
            allowed_sources=secondary_allowed_sources,
        )
        enriched_action["secondary_target_resolution"] = deepcopy(secondary_result)
        if secondary_result.get("resolved"):
            enriched_action["secondary_target_id"] = _safe_str(secondary_result.get("target_id"))
            enriched_action["secondary_target_type"] = _safe_str(secondary_result.get("target_type"))

    if target_ref and not target_result.get("resolved"):
        interaction_result = {
            "resolved": False,
            "changed_state": False,
            "reason": _safe_str(target_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": False,
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "source": "deterministic_general_interaction_runtime",
        }

    if kind == "give" and secondary_ref and not secondary_result.get("resolved"):
        interaction_result = {
            "resolved": False,
            "changed_state": False,
            "reason": "secondary_target_not_resolved",
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "secondary_target_resolution": deepcopy(secondary_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": False,
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "source": "deterministic_general_interaction_runtime",
        }

    inventory_result: Dict[str, Any] = {}
    if kind in {"take", "drop", "give", "equip", "unequip"}:
        inventory_result = apply_inventory_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )

    if inventory_result:
        equipment_stats: Dict[str, Any] = {}
        if kind in {"equip", "unequip"}:
            equipment_stats = project_equipment_stats(simulation_state, actor_id="player")
        companion_item_acceptance_result = _safe_dict(
            inventory_result.get("companion_item_acceptance_result")
        )
        companion_auto_equip_result = _safe_dict(
            inventory_result.get("companion_auto_equip_result")
        )
        interaction_result = {
            "resolved": bool(inventory_result.get("resolved")),
            "changed_state": bool(inventory_result.get("changed_state")),
            "reason": _safe_str(inventory_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "secondary_target_resolution": deepcopy(secondary_result),
            "inventory_result": deepcopy(inventory_result),
            "equipment_stats": deepcopy(equipment_stats),
            "companion_item_acceptance_result": deepcopy(companion_item_acceptance_result),
            "companion_auto_equip_result": deepcopy(companion_auto_equip_result),
            "source": "deterministic_general_interaction_runtime",
        }

        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "inventory_result": deepcopy(inventory_result),
            "equipment_stats": deepcopy(equipment_stats),
            "companion_item_acceptance_result": deepcopy(companion_item_acceptance_result),
            "companion_auto_equip_result": deepcopy(companion_auto_equip_result),
            "source": "deterministic_general_interaction_runtime",
        }

    container_result = {}
    if kind == "put":
        container_result = apply_container_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )
        interaction_result = {
            "resolved": bool(container_result.get("resolved")),
            "changed_state": bool(container_result.get("changed_state")),
            "reason": _safe_str(container_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "secondary_target_resolution": deepcopy(secondary_result),
            "container_result": deepcopy(container_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "container_result": deepcopy(container_result),
            "source": "deterministic_general_interaction_runtime",
        }

    repair_result = {}
    if kind == "repair":
        repair_result = apply_repair_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )
        interaction_result = {
            "resolved": bool(repair_result.get("resolved")),
            "changed_state": bool(repair_result.get("changed_state")),
            "reason": _safe_str(repair_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "secondary_target_resolution": deepcopy(secondary_result),
            "repair_result": deepcopy(repair_result),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "repair_result": deepcopy(repair_result),
            "source": "deterministic_general_interaction_runtime",
        }

    if kind == "consume":
        consumable_result = apply_consumable_interaction(
            simulation_state,
            semantic_action_v2=enriched_action,
            tick=tick,
        )
        equipment_stats = project_equipment_stats(simulation_state, actor_id="player")
        interaction_result = {
            "resolved": bool(consumable_result.get("resolved")),
            "changed_state": bool(consumable_result.get("changed_state")),
            "reason": _safe_str(consumable_result.get("reason")),
            "semantic_action_v2": deepcopy(enriched_action),
            "target_resolution": deepcopy(target_result),
            "secondary_target_resolution": deepcopy(secondary_result),
            "consumable_result": deepcopy(consumable_result),
            "equipment_stats": deepcopy(equipment_stats),
            "source": "deterministic_general_interaction_runtime",
        }
        return {
            "handled": bool(interaction_result.get("resolved")),
            "semantic_action_v2": deepcopy(enriched_action),
            "interaction_result": deepcopy(interaction_result),
            "consumable_result": deepcopy(consumable_result),
            "equipment_stats": deepcopy(equipment_stats),
            "source": "deterministic_general_interaction_runtime",
        }

    interaction_result = {
        "resolved": True,
        "changed_state": False,
        "reason": _interaction_reason_for_kind(kind),
        "semantic_action_v2": deepcopy(enriched_action),
        "target_resolution": deepcopy(target_result),
        "secondary_target_resolution": deepcopy(secondary_result),
        "source": "deterministic_general_interaction_runtime",
    }

    return {
        "handled": bool(interaction_result.get("resolved")),
        "semantic_action_v2": deepcopy(enriched_action),
        "interaction_result": deepcopy(interaction_result),
        "source": "deterministic_general_interaction_runtime",
    }
