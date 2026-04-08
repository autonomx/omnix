"""Tier 21: Alliance System for NPC faction management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AllianceType(Enum):
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"


@dataclass
class Alliance:
    id: str
    members: set = field(default_factory=set)
    alliance_type: AllianceType = AllianceType.FRIENDLY
    created_at: int = 0


class AllianceSystem:
    def __init__(self) -> None:
        self._factions: dict[str, set[str]] = {}
        self._npc_to_faction: dict[str, str] = {}
        self._faction_id_counter = 0

    def form_alliance(self, npc_a: str, npc_b: str, alliance_type: AllianceType = AllianceType.FRIENDLY) -> Optional[str]:
        faction_a = self._npc_to_faction.get(npc_a)
        faction_b = self._npc_to_faction.get(npc_b)

        if faction_a and faction_b:
            if faction_a == faction_b:
                return faction_a
            self._merge_factions(faction_a, faction_b)
            return faction_a

        if faction_a:
            self._factions[faction_a].add(npc_b)
            self._npc_to_faction[npc_b] = faction_a
            return faction_a

        if faction_b:
            self._factions[faction_b].add(npc_a)
            self._npc_to_faction[npc_a] = faction_b
            return faction_b

        faction_id = f"faction_{self._faction_id_counter}"
        self._faction_id_counter += 1
        self._factions[faction_id] = {npc_a, npc_b}
        self._npc_to_faction[npc_a] = faction_id
        self._npc_to_faction[npc_b] = faction_id
        return faction_id

    def break_alliance(self, npc_a: str, npc_b: str) -> None:
        faction_a = self._npc_to_faction.get(npc_a)
        faction_b = self._npc_to_faction.get(npc_b)

        if faction_a == faction_b and faction_a is not None:
            self._factions[faction_a].discard(npc_a)
            self._factions[faction_a].discard(npc_b)
            del self._npc_to_faction[npc_a]
            del self._npc_to_faction[npc_b]
            if not self._factions[faction_a]:
                del self._factions[faction_a]

    def are_allies(self, npc_a: str, npc_b: str) -> bool:
        faction_a = self._npc_to_faction.get(npc_a)
        faction_b = self._npc_to_faction.get(npc_b)
        if faction_a is None or faction_b is None:
            return False
        return faction_a == faction_b

    def get_faction(self, npc: str) -> Optional[str]:
        return self._npc_to_faction.get(npc)

    def get_faction_members(self, npc: str) -> set[str]:
        faction_id = self._npc_to_faction.get(npc)
        if faction_id is None:
            return set()
        members = self._factions.get(faction_id, set())
        return members - {npc}

    def remove_from_faction(self, npc: str) -> None:
        faction_id = self._npc_to_faction.get(npc)
        if faction_id is not None:
            self._factions[faction_id].discard(npc)
            del self._npc_to_faction[npc]
            if not self._factions[faction_id]:
                del self._factions[faction_id]

    def _merge_factions(self, faction_a: str, faction_b: str) -> None:
        members_a = self._factions.pop(faction_a, set())
        members_b = self._factions.pop(faction_b, set())
        merged = members_a | members_b
        self._factions[faction_a] = merged
        for npc in merged:
            self._npc_to_faction[npc] = faction_a
        if not self._factions[faction_a]:
            del self._factions[faction_a]

    def faction_count(self) -> int:
        return len(self._factions)

    def list_factions(self) -> list[dict]:
        result = []
        for fid, members in self._factions.items():
            result.append({"id": fid, "members": list(members)})
        return result

    def clear(self) -> None:
        self._factions.clear()
        self._npc_to_faction.clear()
        self._faction_id_counter = 0