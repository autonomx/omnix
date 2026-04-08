"""Phase 9.0 — Inventory / Item System."""
from __future__ import annotations

from .item_registry import (
    get_item_definition,
    list_item_definitions,
)
from .inventory_state import (
    ensure_inventory_state,
    normalize_inventory_state,
    add_inventory_items,
    remove_inventory_item,
    record_inventory_loot,
    build_inventory_summary,
)
from .item_effects import (
    apply_item_use,
)
from .loot_builder import (
    build_loot_from_encounter_state,
)
from .item_stats import (
    normalize_item_stats,
    is_weapon,
    is_armor,
    is_shield,
    get_weapon_skill,
    get_weapon_attack_stat,
)
from .generated_item_builder import (
    build_item_definition_from_llm,
    clamp_generated_item_stats,
    derive_item_power_band,
)
from .item_registry import normalize_item_definition
from .inventory_state import (
    equip_inventory_item,
    unequip_inventory_slot,
    find_inventory_item,
    get_equipped_weapon,
    get_equipped_armor,
)
from .world_items import (
    ensure_world_item_state,
    spawn_world_item,
    pickup_world_item,
    drop_world_item,
    list_scene_items,
)
from .item_effects import apply_item_effects

__all__ = [
    "get_item_definition",
    "list_item_definitions",
    "ensure_inventory_state",
    "normalize_inventory_state",
    "add_inventory_items",
    "remove_inventory_item",
    "record_inventory_loot",
    "build_inventory_summary",
    "apply_item_use",
    "build_loot_from_encounter_state",
    # Phase 18.3A
    "normalize_item_stats",
    "is_weapon",
    "is_armor",
    "is_shield",
    "get_weapon_skill",
    "get_weapon_attack_stat",
    "build_item_definition_from_llm",
    "clamp_generated_item_stats",
    "derive_item_power_band",
    "normalize_item_definition",
    "equip_inventory_item",
    "unequip_inventory_slot",
    "find_inventory_item",
    "get_equipped_weapon",
    "get_equipped_armor",
    "ensure_world_item_state",
    "spawn_world_item",
    "pickup_world_item",
    "drop_world_item",
    "list_scene_items",
    "apply_item_effects",
]