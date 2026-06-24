"""World pack, lore, and mod overlay validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

LoreScope = Literal["world", "region", "location", "npc", "faction", "item"]
OverlayKind = Literal["item", "service", "npc", "faction", "quest_hook", "prompt_style", "visual_style"]

FORBIDDEN_OVERLAY_KEYS: tuple[str, ...] = ("player_state", "currency", "xp", "combat_hp", "quest_status")


@dataclass(frozen=True)
class LoreEntry:
    key: str
    title: str
    body: str
    scope: LoreScope
    priority: int = 0
    visible: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "body": self.body,
            "scope": self.scope,
            "priority": self.priority,
            "visible": self.visible,
        }


@dataclass(frozen=True)
class ModOverlay:
    overlay_id: str
    kind: OverlayKind
    payload: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {"overlay_id": self.overlay_id, "kind": self.kind, "payload": dict(self.payload)}


@dataclass(frozen=True)
class WorldPack:
    pack_id: str
    title: str
    regions: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    factions: tuple[str, ...] = ()
    npc_templates: tuple[str, ...] = ()
    item_catalogs: tuple[str, ...] = ()
    encounter_tables: tuple[str, ...] = ()
    quest_seeds: tuple[str, ...] = ()
    lore: tuple[LoreEntry, ...] = ()
    overlays: tuple[ModOverlay, ...] = ()

    def with_overlay(self, overlay: ModOverlay) -> "WorldPack":
        return replace(self, overlays=self.overlays + (overlay,))

    def as_dict(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "title": self.title,
            "regions": list(self.regions),
            "locations": list(self.locations),
            "factions": list(self.factions),
            "npc_templates": list(self.npc_templates),
            "item_catalogs": list(self.item_catalogs),
            "encounter_tables": list(self.encounter_tables),
            "quest_seeds": list(self.quest_seeds),
            "lore": [entry.as_dict() for entry in self.lore],
            "overlays": [overlay.as_dict() for overlay in self.overlays],
        }


def validate_lore_entry(entry: LoreEntry) -> tuple[str, ...]:
    issues: list[str] = []
    if not entry.key:
        issues.append("missing_lore_key")
    if not entry.title:
        issues.append("missing_lore_title")
    if not entry.body:
        issues.append("missing_lore_body")
    return tuple(issues)


def validate_overlay(overlay: ModOverlay) -> tuple[str, ...]:
    issues: list[str] = []
    if not overlay.overlay_id:
        issues.append("missing_overlay_id")
    for key in overlay.payload:
        if key in FORBIDDEN_OVERLAY_KEYS:
            issues.append(f"forbidden_overlay_key:{key}")
    return tuple(issues)


def validate_world_pack(pack: WorldPack) -> tuple[str, ...]:
    issues: list[str] = []
    if not pack.pack_id:
        issues.append("missing_pack_id")
    if not pack.title:
        issues.append("missing_title")
    if not pack.regions:
        issues.append("missing_regions")
    for entry in pack.lore:
        issues.extend(validate_lore_entry(entry))
    for overlay in pack.overlays:
        issues.extend(validate_overlay(overlay))
    return tuple(issues)


def visible_lore_for_scope(pack: WorldPack, scope: LoreScope) -> tuple[LoreEntry, ...]:
    entries = [entry for entry in pack.lore if entry.scope == scope and entry.visible]
    return tuple(sorted(entries, key=lambda entry: (-entry.priority, entry.key)))


def world_pack_report(pack: WorldPack) -> dict[str, object]:
    return {"pack": pack.as_dict(), "validation_issues": list(validate_world_pack(pack))}
