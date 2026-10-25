"""Deterministic allocation of major global World Forge anchor identities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AnchorSlot:
    id: str
    domain_id: str
    anchor_kind: str
    slot_index: int
    anchor_role: str = ""

    def as_dict(self) -> dict[str, Any]:
        row = {
            "id": self.id,
            "domain_id": self.domain_id,
            "anchor_kind": self.anchor_kind,
            "slot_index": self.slot_index,
        }
        if self.anchor_role:
            row["anchor_role"] = self.anchor_role
        return row


# Domain -> (anchor kind, ID prefix). Every entity a domain's topic is asked
# for gets an anchor: topic generation requires one authoritative ID per
# entity, so a cap below the graph's target count made generation fail.


def anchor_slice_for_domain(
    domain_id: str,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    anchors = [
        dict(row)
        for row in registry.get("anchors") or ()
        if isinstance(row, Mapping) and str(row.get("domain_id") or "") == domain_id
    ]
    return {
        "schema_version": str(registry.get("schema_version") or ""),
        "registry_hash": str(registry.get("registry_hash") or ""),
        "anchors": anchors,
    }


__all__ = ["AnchorSlot", "anchor_slice_for_domain"]
