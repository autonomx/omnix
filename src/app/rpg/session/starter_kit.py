"""Deterministic starter-kit parsing for RPG new-game summaries."""
from __future__ import annotations

from typing import Any

DEFAULT_CURRENCY = {"gold": 10, "silver": 25, "copper": 50}
DEFAULT_EQUIPMENT = [
    {"slot": "Weapon", "name": "Iron dagger"},
    {"slot": "Ranged", "name": "Simple bow"},
    {"slot": "Cloak", "name": "Traveler's cloak"},
]
DEFAULT_INVENTORY: list[dict[str, Any]] = [
    {"id": "travelers_cloak", "name": "Traveler's cloak", "quantity": 1, "type": "clothing"},
    {"id": "bedroll", "name": "Bedroll", "quantity": 1, "type": "camping"},
    {"id": "waterskin", "name": "Waterskin", "quantity": 1, "type": "supply"},
    {"id": "ration", "name": "Ration", "quantity": 3, "type": "food"},
    {"id": "torch", "name": "Torch", "quantity": 2, "type": "tool"},
    {"id": "iron_dagger", "name": "Iron dagger", "quantity": 1, "type": "weapon"},
    {"id": "simple_bow", "name": "Simple bow", "quantity": 1, "type": "weapon"},
    {"id": "arrow", "name": "Arrow", "quantity": 20, "type": "ammo"},
    {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"},
]

STARTER_ITEM_CATALOG: dict[str, dict[str, Any]] = {
    "travel cloak": {"id": "travelers_cloak", "name": "Traveler's cloak", "type": "clothing", "slot": "Cloak"},
    "fine cloak": {"id": "fine_cloak", "name": "Fine cloak", "type": "clothing", "slot": "Cloak"},
    "iron dagger": {"id": "iron_dagger", "name": "Iron dagger", "type": "weapon", "slot": "Weapon"},
    "shortbow": {"id": "shortbow", "name": "Shortbow", "type": "weapon", "slot": "Ranged"},
    "hand axe": {"id": "hand_axe", "name": "Hand axe", "type": "weapon", "slot": "Weapon"},
    "arrow bundle": {"id": "arrow", "name": "Arrow", "quantity": 20, "type": "ammo"},
    "bedroll": {"id": "bedroll", "name": "Bedroll", "type": "camping"},
    "trail rations": {"id": "ration", "name": "Ration", "type": "food"},
    "rations": {"id": "ration", "name": "Ration", "type": "food"},
    "torch": {"id": "torch", "name": "Torch", "type": "tool"},
    "field kit": {"id": "field_kit", "name": "Field kit", "type": "tool"},
    "rope coil": {"id": "rope_coil", "name": "Rope coil", "type": "tool"},
    "ledger note": {"id": "ledger_note", "name": "Ledger note", "type": "quest"},
    "field journal": {"id": "field_journal", "name": "Field journal", "type": "quest"},
    "ink kit": {"id": "ink_kit", "name": "Ink kit", "type": "tool"},
    "old map": {"id": "old_map", "name": "Old map", "type": "quest"},
    "journal": {"id": "journal", "name": "Journal", "type": "quest"},
}


def summary_field(summary: str | None, field_name: str) -> str | None:
    if not summary:
        return None
    marker = f"{field_name}:"
    start = summary.lower().find(marker.lower())
    if start < 0:
        return None
    start += len(marker)
    end = summary.find(".", start)
    value = summary[start : end if end >= 0 else len(summary)].strip()
    return value or None


def _catalog_key(value: str) -> str:
    return value.strip().lower().replace("'", "").replace("’", "")


def _split_quantity(raw: str) -> tuple[str, int]:
    text = raw.strip()
    marker = " x"
    index = text.lower().rfind(marker)
    if index >= 0:
        amount = text[index + len(marker) :].strip()
        if amount.isdigit():
            return text[:index].strip(), max(1, int(amount))
    return text, 1


def _add_inventory_item(items_by_id: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    item_id = str(item["id"])
    if item_id in items_by_id:
        items_by_id[item_id]["quantity"] = int(items_by_id[item_id].get("quantity", 1)) + int(item.get("quantity", 1))
        return
    items_by_id[item_id] = dict(item)


def _parse_currency(raw: str, currency: dict[str, int]) -> bool:
    parts = raw.strip().lower().split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in currency:
        return False
    currency[parts[1]] += int(parts[0])
    return True


def build_starter_kit(summary: str | None) -> dict[str, Any]:
    starter_text = summary_field(summary, "Starter gear")
    if not starter_text:
        return {
            "source": "default",
            "currency": dict(DEFAULT_CURRENCY),
            "equipment": [dict(item) for item in DEFAULT_EQUIPMENT],
            "inventory": [dict(item) for item in DEFAULT_INVENTORY],
            "items": [item["name"] for item in DEFAULT_INVENTORY],
        }
    currency = {"gold": 0, "silver": 0, "copper": 0}
    items_by_id: dict[str, dict[str, Any]] = {}
    equipment: list[dict[str, str]] = []
    equipped_slots: set[str] = set()
    source_items: list[str] = []
    for raw in [part.strip() for part in starter_text.split(",") if part.strip()]:
        if _parse_currency(raw, currency):
            source_items.append(raw)
            continue
        name, requested_quantity = _split_quantity(raw)
        catalog = STARTER_ITEM_CATALOG.get(_catalog_key(name)) or {"id": _catalog_key(name).replace(" ", "_"), "name": name, "type": "misc"}
        quantity = int(catalog.get("quantity", requested_quantity))
        item = {key: value for key, value in catalog.items() if key not in {"slot", "quantity"}}
        item["quantity"] = quantity
        _add_inventory_item(items_by_id, item)
        slot = catalog.get("slot")
        if isinstance(slot, str) and slot not in equipped_slots:
            equipment.append({"slot": slot, "name": str(catalog.get("name", name))})
            equipped_slots.add(slot)
        source_items.append(raw)
    if "journal" not in items_by_id and "field_journal" not in items_by_id:
        _add_inventory_item(items_by_id, {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"})
    return {"source": "generated_class_summary", "currency": currency, "equipment": equipment, "inventory": list(items_by_id.values()), "items": source_items}
