"""Phase 7.9 — Pack Registry.

Explicit in-memory registry of loaded/available packs.
Snapshot-safe and deterministic.
"""

from __future__ import annotations

from .models import AdventurePack


class PackRegistry:
    """In-memory registry of adventure packs."""

    def __init__(self) -> None:
        self.packs: dict[str, AdventurePack] = {}

    def register(self, pack: AdventurePack) -> None:
        """Register a pack by its pack_id."""
        pack_id = pack.metadata.pack_id

        if pack_id in self.packs:
            existing = self.packs[pack_id]
            if existing.metadata.version != pack.metadata.version:
                raise ValueError(f"pack_version_conflict:{pack_id}")

        self.packs[pack_id] = pack

    def remove(self, pack_id: str) -> None:
        """Remove a pack from the registry."""
        self.packs.pop(pack_id, None)

    def get(self, pack_id: str) -> AdventurePack | None:
        """Get a pack by ID, or None if not found."""
        return self.packs.get(pack_id)

    def list_packs(self) -> list[AdventurePack]:
        """Return all registered packs in deterministic order."""
        return [self.packs[k] for k in sorted(self.packs.keys())]

    def serialize_state(self) -> dict:
        """Serialize the registry for snapshot persistence."""
        return {
            "packs": {
                pack_id: pack.to_dict()
                for pack_id, pack in sorted(self.packs.items())
            }
        }

    def deserialize_state(self, data: dict) -> None:
        """Restore registry state from a serialized snapshot."""
        self.packs = {
            pack_id: AdventurePack.from_dict(pack_data)
            for pack_id, pack_data in data.get("packs", {}).items()
        }
