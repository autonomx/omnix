"""Phase 7.9 — Adventure Packs — Regression Tests.

Ensures:
- Pack loading/merging is deterministic
- Registry survives snapshot restore
- Malformed packs do not register
- Pack operations do not mutate runtime truth directly
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.packs.exporter import PackExporter
from app.rpg.packs.loader import PackLoader
from app.rpg.packs.merger import PackMergeConflictError, PackMerger
from app.rpg.packs.models import (
    AdventurePack,
    PackContent,
    PackManifest,
    PackMetadata,
)
from app.rpg.packs.registry import PackRegistry
from app.rpg.packs.validator import PackValidator

# ======================================================================
# Helpers
# ======================================================================


def _make_pack(
    pack_id: str = "test_pack",
    title: str = "Test Pack",
    version: str = "1.0.0",
    **content_kwargs,
) -> AdventurePack:
    return AdventurePack(
        metadata=PackMetadata(pack_id=pack_id, title=title, version=version),
        manifest=PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        ),
        content=PackContent(**content_kwargs),
    )


# ======================================================================
# Determinism Tests
# ======================================================================


class TestPackMergeIsDeterministic:
    def test_merge_order_produces_same_result(self):
        """Merging the same packs in the same order always produces identical output."""
        p1 = _make_pack(
            pack_id="alpha",
            factions=[{"faction_id": "f1", "name": "A"}],
            npcs=[{"npc_id": "n1", "name": "N1"}],
        )
        p2 = _make_pack(
            pack_id="beta",
            factions=[{"faction_id": "f2", "name": "B"}],
            locations=[{"location_id": "l1", "name": "L1"}],
        )

        merger = PackMerger()
        result_a = merger.merge([p1, p2])
        result_b = merger.merge([p1, p2])

        assert result_a.to_dict() == result_b.to_dict()

    def test_load_produces_deterministic_payload(self):
        """Loading the same pack always produces the same seed payload."""
        pack = _make_pack(
            pack_id="det",
            factions=[{"faction_id": "f1"}],
            arcs=[{"arc_id": "a1"}],
            social_seeds=[{"type": "rumor", "content": "test"}],
        )

        loader = PackLoader()
        payload_a = loader.load(pack)
        payload_b = loader.load(pack)

        assert payload_a == payload_b


# ======================================================================
# Snapshot / Registry Persistence Tests
# ======================================================================


class TestPackRegistrySurvivesSnapshotRestore:
    def test_full_roundtrip(self):
        """Registry state serializes and deserializes correctly."""
        registry = PackRegistry()
        registry.register(_make_pack(
            pack_id="p1",
            factions=[{"faction_id": "f1", "name": "Order"}],
            npcs=[{"npc_id": "n1", "name": "Hero"}],
        ))
        registry.register(_make_pack(
            pack_id="p2",
            locations=[{"location_id": "l1", "name": "Tavern"}],
        ))

        snapshot = registry.serialize_state()

        # Restore into a fresh registry
        new_registry = PackRegistry()
        new_registry.deserialize_state(snapshot)

        assert len(new_registry.list_packs()) == 2
        p1 = new_registry.get("p1")
        assert p1 is not None
        assert p1.content.factions[0]["faction_id"] == "f1"
        p2 = new_registry.get("p2")
        assert p2 is not None
        assert p2.content.locations[0]["location_id"] == "l1"

    def test_double_roundtrip(self):
        """Double snapshot roundtrip produces identical state."""
        registry = PackRegistry()
        registry.register(_make_pack(pack_id="p1", factions=[{"faction_id": "f1"}]))

        snap1 = registry.serialize_state()
        r2 = PackRegistry()
        r2.deserialize_state(snap1)
        snap2 = r2.serialize_state()

        assert snap1 == snap2


# ======================================================================
# Malformed Pack Rejection Tests
# ======================================================================


class TestInvalidPackIsNotRegistered:
    def test_missing_pack_id_rejected(self):
        """A pack with no pack_id is rejected by validation."""
        pack = _make_pack(pack_id="")
        validator = PackValidator()
        result = validator.validate(pack)
        assert result.is_blocking()

    def test_malformed_content_rejected(self):
        """A pack with non-dict content items is rejected."""
        pack = _make_pack()
        pack.content.factions = ["not_a_dict"]
        validator = PackValidator()
        result = validator.validate(pack)
        assert result.is_blocking()

    def test_duplicate_ids_rejected(self):
        """A pack with duplicate content IDs is rejected."""
        pack = _make_pack(factions=[
            {"faction_id": "f1", "name": "A"},
            {"faction_id": "f1", "name": "B"},
        ])
        validator = PackValidator()
        result = validator.validate(pack)
        assert result.is_blocking()

    def test_register_flow_rejects_invalid(self):
        """Full register flow rejects invalid pack and does not add to registry."""
        registry = PackRegistry()
        validator = PackValidator()

        pack_data = {
            "metadata": {"pack_id": "", "title": "", "version": ""},
            "manifest": {"manifest_id": "", "pack_id": "", "content_version": ""},
            "content": {},
        }
        pack = AdventurePack.from_dict(pack_data)
        result = validator.validate(pack)
        if not result.is_blocking():
            registry.register(pack)
        # Should NOT be registered
        assert registry.get("") is None
        assert len(registry.list_packs()) == 0


# ======================================================================
# No Runtime Truth Mutation Tests
# ======================================================================


class TestPackLoadingDoesNotMutateRuntimeTruth:
    def test_loading_pack_does_not_mutate_pack_data(self):
        """Loading a pack returns a payload without modifying the original pack."""
        pack = _make_pack(
            pack_id="immutable",
            factions=[{"faction_id": "f1", "name": "Order"}],
        )
        original_dict = copy.deepcopy(pack.to_dict())

        loader = PackLoader()
        _ = loader.load(pack)

        assert pack.to_dict() == original_dict

    def test_merging_does_not_mutate_source_packs(self):
        """Merging packs does not mutate the source pack objects."""
        p1 = _make_pack(pack_id="a", factions=[{"faction_id": "f1"}])
        p2 = _make_pack(pack_id="b", factions=[{"faction_id": "f2"}])

        p1_dict = copy.deepcopy(p1.to_dict())
        p2_dict = copy.deepcopy(p2.to_dict())

        merger = PackMerger()
        _ = merger.merge([p1, p2])

        assert p1.to_dict() == p1_dict
        assert p2.to_dict() == p2_dict

    def test_load_payload_is_independent_of_pack(self):
        """Modifying the load payload does not affect the source pack."""
        pack = _make_pack(
            pack_id="p1",
            factions=[{"faction_id": "f1", "name": "A"}],
        )

        loader = PackLoader()
        payload = loader.load(pack)

        # Mutate payload
        payload["creator_seed"]["factions"].append({"faction_id": "f_new"})

        # Pack should be unchanged
        assert len(pack.content.factions) == 1

    def test_registry_serialization_is_independent_copy(self):
        """Serialized state is an independent copy — mutating it doesn't affect registry."""
        registry = PackRegistry()
        registry.register(_make_pack(pack_id="p1"))

        snapshot = registry.serialize_state()
        snapshot["packs"]["p1"]["metadata"]["title"] = "MUTATED"

        # Registry should be unaffected
        assert registry.get("p1").metadata.title == "Test Pack"
