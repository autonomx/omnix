"""Phase 8.5 — Functional Tests for Save Migration / Packaging Interoperability.

End-to-end migration workflows covering save and pack migration,
version stamping, legacy upgrades, and pipeline composition.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest \
        tests/functional/test_phase85_migration_functional.py -v --noconftest
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.migration.models import (
    CURRENT_PACK_FORMAT_VERSION,
    CURRENT_SAVE_FORMAT_VERSION,
    CompatibilityReport,
    MigratedPayload,
    MigrationReport,
)
from app.rpg.migration.pack_migrator import PackMigrator
from app.rpg.migration.registry import MigrationRegistry
from app.rpg.migration.save_migrator import SaveMigrator, build_default_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _legacy_save_payload() -> dict:
    """A minimal old-style save with no version stamp."""
    return {
        "coherence_core": {"facts": ["the sky is blue"]},
        "social_state_core": {"rumors": []},
        "packs": {"starter_pack": {"id": "starter_pack"}},
    }


def _legacy_pack_payload() -> dict:
    """An old-style pack with no version stamp."""
    return {
        "metadata": {"pack_id": "old_pack", "title": "Old Pack"},
        "content": {"scenes": {"intro": {"text": "Welcome"}}},
    }


def _current_save_payload() -> dict:
    """A payload already at the current save format version."""
    payload: dict = {"save_format_version": CURRENT_SAVE_FORMAT_VERSION}
    for section in (
        "coherence_core", "social_state_core", "campaign_memory_core",
        "arc_control_controller", "encounter_controller",
        "world_sim_controller", "pack_registry", "recovery_manager",
        "creator_state",
    ):
        payload[section] = {}
    payload["runtime_cache"] = {
        "last_dialogue_response": None,
        "last_world_sim_result": None,
        "last_debug_bundle": None,
        "last_dialogue_trace": None,
        "last_control_output": None,
        "last_action_result": None,
        "last_encounter_resolution": None,
    }
    payload["engine_metadata"] = {}
    return payload


_AUTHORITATIVE_SECTIONS = frozenset({
    "coherence_core", "social_state_core", "campaign_memory_core",
    "arc_control_controller", "encounter_controller",
    "world_sim_controller", "pack_registry", "recovery_manager",
    "creator_state",
})

_RUNTIME_CACHE_KEYS = frozenset({
    "last_dialogue_response", "last_world_sim_result",
    "last_debug_bundle", "last_dialogue_trace",
    "last_control_output", "last_action_result",
    "last_encounter_resolution",
})


# ===================================================================
# 1. Load legacy save successfully
# ===================================================================

class TestLoadLegacySave:
    """Legacy saves (no version) migrate to the current format."""

    def test_legacy_save_upgrades_to_current_version(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())

        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION
        assert result.report.original_version == 0
        assert result.report.final_version == CURRENT_SAVE_FORMAT_VERSION

    def test_key_sections_exist_after_migration(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        payload = result.payload

        for section in _AUTHORITATIVE_SECTIONS:
            assert section in payload, f"Missing section: {section}"
            assert isinstance(payload[section], dict)

        assert "runtime_cache" in payload
        assert "engine_metadata" in payload

    def test_legacy_report_has_no_errors(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())

        assert result.report.errors == []
        assert len(result.report.applied_steps) >= 1
        assert result.report.scope == "save"


# ===================================================================
# 2. Save current loop writes current version
# ===================================================================

class TestSaveCurrentVersion:
    """A payload already at the current version passes through unchanged."""

    def test_current_version_passes_through(self):
        migrator = SaveMigrator()
        payload = _current_save_payload()
        result = migrator.migrate(payload)

        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION
        assert result.report.errors == []
        assert result.report.applied_steps == []

    def test_version_stamp_is_correct(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_current_save_payload())

        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION

    def test_sections_preserved_for_current_version(self):
        migrator = SaveMigrator()
        original = _current_save_payload()
        original["coherence_core"] = {"facts": ["test_fact"]}
        result = migrator.migrate(original)

        assert result.payload["coherence_core"]["facts"] == ["test_fact"]


# ===================================================================
# 3. Register legacy pack through migration
# ===================================================================

class TestRegisterLegacyPack:
    """Old pack payloads (no version) upgrade successfully."""

    def test_legacy_pack_upgrades_to_current_version(self):
        migrator = PackMigrator()
        result = migrator.migrate(_legacy_pack_payload())

        assert result.payload["pack_format_version"] == CURRENT_PACK_FORMAT_VERSION
        assert result.report.errors == []

    def test_pack_metadata_normalized(self):
        migrator = PackMigrator()
        result = migrator.migrate(_legacy_pack_payload())
        meta = result.payload["metadata"]

        assert meta["pack_id"] == "old_pack"
        assert meta["title"] == "Old Pack"
        assert "version" in meta

    def test_pack_format_version_stamped(self):
        migrator = PackMigrator()
        result = migrator.migrate(_legacy_pack_payload())

        assert result.payload["pack_format_version"] == CURRENT_PACK_FORMAT_VERSION

    def test_pack_content_preserved(self):
        migrator = PackMigrator()
        result = migrator.migrate(_legacy_pack_payload())

        assert "content" in result.payload
        assert "scenes" in result.payload["content"]


# ===================================================================
# 4. Incompatible pack rejected with structured report
# ===================================================================

class TestIncompatiblePackRejected:
    """Future-version or engine-incompatible packs are rejected."""

    def test_future_version_pack_rejected(self):
        migrator = PackMigrator()
        pack = {"pack_format_version": CURRENT_PACK_FORMAT_VERSION + 10, "metadata": {}}
        compat = migrator.check_compatibility(pack)

        assert compat.compatible is False
        assert len(compat.errors) >= 1
        assert any("newer" in e for e in compat.errors)

    def test_engine_constraint_min_violation(self):
        migrator = PackMigrator()
        pack = {
            "metadata": {"pack_id": "strict"},
            "content": {},
            "engine_compatibility": {
                "min_save_format_version": CURRENT_SAVE_FORMAT_VERSION + 5,
            },
        }
        compat = migrator.check_compatibility(pack)

        assert compat.compatible is False
        assert any("min_save_format_version" in e for e in compat.errors)

    def test_engine_constraint_max_violation(self):
        migrator = PackMigrator()
        pack = {
            "metadata": {"pack_id": "old_engine"},
            "content": {},
            "engine_compatibility": {
                "max_save_format_version": 0,
            },
        }
        compat = migrator.check_compatibility(pack)

        assert compat.compatible is False
        assert any("max_save_format_version" in e for e in compat.errors)

    def test_report_is_inspectable(self):
        migrator = PackMigrator()
        pack = {"pack_format_version": 999, "metadata": {}}
        compat = migrator.check_compatibility(pack)

        report_dict = compat.to_dict()
        assert isinstance(report_dict, dict)
        assert "compatible" in report_dict
        assert "errors" in report_dict
        assert report_dict["compatible"] is False


# ===================================================================
# 5. Derived caches can be reset safely
# ===================================================================

class TestDerivedCacheReset:
    """Older saves missing runtime caches still migrate correctly."""

    def test_missing_runtime_cache_created(self):
        migrator = SaveMigrator()
        payload = {"coherence_core": {}}  # v0, no runtime_cache
        result = migrator.migrate(payload)

        assert "runtime_cache" in result.payload
        cache = result.payload["runtime_cache"]
        for key in _RUNTIME_CACHE_KEYS:
            assert key in cache

    def test_runtime_cache_defaults_to_none(self):
        migrator = SaveMigrator()
        result = migrator.migrate({"coherence_core": {}})
        cache = result.payload["runtime_cache"]

        for key in _RUNTIME_CACHE_KEYS:
            assert cache[key] is None

    def test_partial_cache_filled(self):
        migrator = SaveMigrator()
        payload = {
            "save_format_version": 1,
            "runtime_cache": {"last_dialogue_response": "hello"},
        }
        result = migrator.migrate(payload)
        cache = result.payload["runtime_cache"]

        assert cache["last_dialogue_response"] == "hello"
        for key in _RUNTIME_CACHE_KEYS - {"last_dialogue_response"}:
            assert cache[key] is None


# ===================================================================
# 6. Full migration pipeline
# ===================================================================

class TestFullMigrationPipeline:
    """Complex multi-step migration scenarios."""

    def test_complex_legacy_save_migrates_0_to_2(self):
        payload = {
            "coherence_core": {"facts": ["dragon exists"]},
            "social_state_core": {"rumors": [{"id": "r1"}]},
            "packs": {"starter": {"id": "starter"}},
            "campaign_memory_core": {"events": []},
            "custom_field": "preserve_me",
        }
        migrator = SaveMigrator()
        result = migrator.migrate(payload)

        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION
        assert result.report.original_version == 0
        assert result.report.final_version == CURRENT_SAVE_FORMAT_VERSION
        assert result.report.errors == []

        # All authoritative sections present
        for section in _AUTHORITATIVE_SECTIONS:
            assert section in result.payload

        # Runtime cache present with all keys
        assert "runtime_cache" in result.payload
        for key in _RUNTIME_CACHE_KEYS:
            assert key in result.payload["runtime_cache"]

        assert len(result.report.applied_steps) == 2

    def test_pack_migration_preserves_content_through_hops(self):
        pack = {
            "metadata": {"pack_id": "adventure_1", "title": "Adventure One"},
            "content": {
                "scenes": {"battle": {"enemies": 3}},
                "items": {"sword": {"damage": 10}},
            },
        }
        migrator = PackMigrator()
        result = migrator.migrate(pack)

        assert result.payload["pack_format_version"] == CURRENT_PACK_FORMAT_VERSION
        content = result.payload["content"]
        assert content["scenes"]["battle"]["enemies"] == 3
        assert content["items"]["sword"]["damage"] == 10
        assert result.report.errors == []

    def test_combined_save_and_pack_migration(self):
        save_migrator = SaveMigrator()
        pack_migrator = PackMigrator()

        save_result = save_migrator.migrate(_legacy_save_payload())
        pack_result = pack_migrator.migrate(_legacy_pack_payload())

        assert save_result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION
        assert pack_result.payload["pack_format_version"] == CURRENT_PACK_FORMAT_VERSION
        assert save_result.report.errors == []
        assert pack_result.report.errors == []

    def test_shared_registry_handles_both_scopes(self):
        registry = build_default_registry()

        assert registry.has_path("save", 0, CURRENT_SAVE_FORMAT_VERSION)
        assert registry.has_path("pack", 0, CURRENT_PACK_FORMAT_VERSION)

        save_path = registry.get_save_path(0, CURRENT_SAVE_FORMAT_VERSION)
        pack_path = registry.get_pack_path(0, CURRENT_PACK_FORMAT_VERSION)

        assert len(save_path) == CURRENT_SAVE_FORMAT_VERSION
        assert len(pack_path) == CURRENT_PACK_FORMAT_VERSION
