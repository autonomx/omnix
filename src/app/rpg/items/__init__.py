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
]