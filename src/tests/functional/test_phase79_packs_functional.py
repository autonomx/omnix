"""Phase 7.9 — Adventure Packs — Functional Tests.

End-to-end tests verifying pack operations through the GameLoop
integration layer: register, list, load, merge, export.
"""

from __future__ import annotations

import pytest

from app.rpg.packs.exporter import PackExporter
from app.rpg.packs.loader import PackLoader
from app.rpg.packs.merger import PackMerger
from app.rpg.packs.models import (
    AdventurePack,
    PackContent,
    PackManifest,
    PackMetadata,
)
from app.rpg.packs.presenters import PackPresenter
from app.rpg.packs.registry import PackRegistry
from app.rpg.packs.validator import PackValidator

# ======================================================================
# Helpers
# ======================================================================


def _make_pack_data(
    pack_id: str = "test_pack",
    title: str = "Test Pack",
    version: str = "1.0.0",
    factions: list | None = None,
    npcs: list | None = None,
    locations: list | None = None,
    arcs: list | None = None,
    social_seeds: list | None = None,
) -> dict:
    """Build a raw pack dict suitable for register_pack()."""
    return {
        "metadata": {
            "pack_id": pack_id,
            "title": title,
            "version": version,
        },
        "manifest": {
            "manifest_id": f"{pack_id}_manifest",
            "pack_id": pack_id,
            "content_version": version,
        },
        "content": {
            "creator_facts": [],
            "setup_templates": [],
            "factions": factions or [],
            "locations": locations or [],
            "npcs": npcs or [],
            "threads": [],
            "arcs": arcs or [],
            "social_seeds": social_seeds or [],
            "reveal_seeds": [],
            "pacing_presets": [],
            "gm_presets": [],
        },
    }


class _MockPackOps:
    """Simulates GameLoop pack operations without full GameLoop init."""

    def __init__(self):
        self.pack_registry = PackRegistry()
        self.pack_validator = PackValidator()
        self.pack_loader = PackLoader()
        self.pack_merger = PackMerger()
        self.pack_exporter = PackExporter()
        self.pack_presenter = PackPresenter()

    def register_pack(self, pack_data: dict) -> dict:
        pack = AdventurePack.from_dict(pack_data)
        validation = self.pack_validator.validate(pack)
        validation_dict = validation.to_dict()
        presented_validation = self.pack_presenter.present_validation_result(validation_dict)
        if validation.is_blocking():
            return {"ok": False, "validation": presented_validation}
        self.pack_registry.register(pack)
        return {
            "ok": True,
            "validation": presented_validation,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
        }

    def list_registered_packs(self) -> dict:
        packs = self.pack_registry.list_packs()
        return self.pack_presenter.present_pack_list([p.to_dict() for p in packs])

    def load_registered_packs(self, pack_ids: list[str]) -> dict:
        packs = []
        missing = []
        for pid in pack_ids:
            p = self.pack_registry.get(pid)
            if p is None:
                missing.append(pid)
            else:
                packs.append(p)
        if missing:
            return {"ok": False, "reason": "missing_packs", "missing": missing}
        payload = self.pack_loader.load_many(packs)
        return {
            "ok": True,
            "payload": payload,
            "presented": self.pack_presenter.present_load_result(payload),
        }

    def merge_registered_packs(self, pack_ids: list[str]) -> dict:
        packs = []
        missing = []
        for pid in pack_ids:
            p = self.pack_registry.get(pid)
            if p is None:
                missing.append(pid)
            else:
                packs.append(p)
        if missing:
            return {"ok": False, "reason": "missing_packs", "missing": missing}
        try:
            merged = self.pack_merger.merge(packs)
        except Exception as exc:
            return {"ok": False, "reason": "merge_conflict", "error": str(exc)}
        return {
            "ok": True,
            "pack": self.pack_presenter.present_pack(merged.to_dict()),
            "pack_data": merged.to_dict(),
        }

    def export_current_setup_as_pack(self, title: str, version: str, pack_id: str) -> dict:
        pack = self.pack_exporter.export_minimal(title, version, pack_id)
        return {
            "ok": True,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
            "pack_data": pack.to_dict(),
        }


# ======================================================================
# Functional Tests
# ======================================================================


class TestRegisterPackReturnsValidationAndRegistersPack:
    def test_valid_pack_registers_successfully(self):
        ops = _MockPackOps()
        data = _make_pack_data(pack_id="p1", factions=[{"faction_id": "f1", "name": "G"}])
        result = ops.register_pack(data)
        assert result["ok"] is True
        assert result["validation"]["is_blocking"] is False
        assert result["pack"]["pack_id"] == "p1"
        # Pack should be in registry
        assert ops.pack_registry.get("p1") is not None

    def test_invalid_pack_rejected(self):
        ops = _MockPackOps()
        data = _make_pack_data(pack_id="", title="")
        result = ops.register_pack(data)
        assert result["ok"] is False
        assert result["validation"]["is_blocking"] is True


class TestListRegisteredPacksReturnsPresentedPayload:
    def test_returns_presented_list(self):
        ops = _MockPackOps()
        ops.register_pack(_make_pack_data(pack_id="alpha", title="Alpha"))
        ops.register_pack(_make_pack_data(pack_id="beta", title="Beta"))
        result = ops.list_registered_packs()
        assert result["title"] == "Adventure Packs"
        assert result["count"] == 2
        ids = [item["pack_id"] for item in result["items"]]
        assert "alpha" in ids
        assert "beta" in ids


class TestLoadRegisteredPacksReturnsSeedPayload:
    def test_load_returns_seed_sections(self):
        ops = _MockPackOps()
        ops.register_pack(_make_pack_data(
            pack_id="p1",
            factions=[{"faction_id": "f1", "name": "G"}],
            npcs=[{"npc_id": "n1", "name": "H"}],
        ))
        result = ops.load_registered_packs(["p1"])
        assert result["ok"] is True
        assert "creator_seed" in result["payload"]
        assert "arc_seed" in result["payload"]
        assert "social_seed" in result["payload"]
        assert "memory_seed" in result["payload"]

    def test_load_missing_pack_fails(self):
        ops = _MockPackOps()
        result = ops.load_registered_packs(["nonexistent"])
        assert result["ok"] is False
        assert result["reason"] == "missing_packs"


class TestMergeRegisteredPacksReturnsMergedPackPayload:
    def test_merge_two_packs(self):
        ops = _MockPackOps()
        ops.register_pack(_make_pack_data(
            pack_id="a", factions=[{"faction_id": "f1"}],
        ))
        ops.register_pack(_make_pack_data(
            pack_id="b", factions=[{"faction_id": "f2"}],
        ))
        result = ops.merge_registered_packs(["a", "b"])
        assert result["ok"] is True
        assert "pack" in result
        assert "pack_data" in result

    def test_merge_conflicting_packs_fails(self):
        ops = _MockPackOps()
        ops.register_pack(_make_pack_data(
            pack_id="a", factions=[{"faction_id": "f1", "name": "A"}],
        ))
        ops.register_pack(_make_pack_data(
            pack_id="b", factions=[{"faction_id": "f1", "name": "B"}],
        ))
        result = ops.merge_registered_packs(["a", "b"])
        assert result["ok"] is False
        assert result["reason"] == "merge_conflict"


class TestExportCurrentSetupAsPackReturnsPackPayload:
    def test_export_returns_valid_pack(self):
        ops = _MockPackOps()
        result = ops.export_current_setup_as_pack("Exported", "1.0", "exp1")
        assert result["ok"] is True
        assert result["pack"]["pack_id"] == "exp1"
        assert "pack_data" in result

    def test_exported_pack_can_be_registered(self):
        ops = _MockPackOps()
        result = ops.export_current_setup_as_pack("E", "1.0", "e1")
        reg_result = ops.register_pack(result["pack_data"])
        assert reg_result["ok"] is True
