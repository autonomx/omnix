"""Phase 8.5 — Regression Tests for Save Migration / Packaging Interoperability.

Protect architecture invariants: determinism, field preservation,
serialization round-trips, and failure clarity.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest \
        tests/regression/test_phase85_migration_regression.py -v --noconftest
"""

from __future__ import annotations

import copy
import json

import pytest

from app.rpg.migration.models import (
    CURRENT_PACK_FORMAT_VERSION,
    CURRENT_SAVE_FORMAT_VERSION,
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
    return {
        "coherence_core": {"facts": ["dragon exists"]},
        "social_state_core": {"rumors": []},
        "packs": {"starter": {"id": "starter"}},
    }


def _legacy_pack_payload() -> dict:
    return {
        "metadata": {"pack_id": "test_pack", "title": "Test Pack"},
        "content": {"scenes": {"intro": {"text": "Hello"}}},
    }


# ===================================================================
# 1. Migration is deterministic
# ===================================================================

class TestMigrationDeterministic:
    """Identical inputs must always produce identical outputs."""

    def test_same_save_input_produces_identical_payload(self):
        migrator = SaveMigrator()
        result1 = migrator.migrate(copy.deepcopy(_legacy_save_payload()))
        result2 = migrator.migrate(copy.deepcopy(_legacy_save_payload()))

        assert result1.payload == result2.payload

    def test_same_save_input_produces_identical_report(self):
        migrator = SaveMigrator()
        result1 = migrator.migrate(copy.deepcopy(_legacy_save_payload()))
        result2 = migrator.migrate(copy.deepcopy(_legacy_save_payload()))

        assert result1.report.to_dict() == result2.report.to_dict()

    def test_multiple_runs_produce_same_output(self):
        migrator = SaveMigrator()
        results = [
            migrator.migrate(copy.deepcopy(_legacy_save_payload()))
            for _ in range(5)
        ]

        first_payload = results[0].payload
        first_report = results[0].report.to_dict()
        for r in results[1:]:
            assert r.payload == first_payload
            assert r.report.to_dict() == first_report


# ===================================================================
# 2. Migration does not silently discard unknown fields
# ===================================================================

class TestUnknownFieldPreservation:
    """Unknown top-level keys are preserved, not silently dropped."""

    def test_unknown_save_keys_preserved_in_extras(self):
        migrator = SaveMigrator()
        payload = _legacy_save_payload()
        payload["custom_user_data"] = {"notes": "important"}
        result = migrator.migrate(payload)

        extras = result.payload.get("_extras", {})
        assert "custom_user_data" in extras or "custom_user_data" in result.payload

    def test_unknown_pack_keys_preserved_in_extras(self):
        migrator = PackMigrator()
        pack = _legacy_pack_payload()
        pack["custom_module"] = {"data": 42}
        result = migrator.migrate(pack)

        extras = result.payload.get("_extras", {})
        assert "custom_module" in extras or "custom_module" in result.payload

    def test_migration_metadata_records_preserved_keys(self):
        migrator = SaveMigrator()
        payload = _legacy_save_payload()
        payload["exotic_field"] = "keep"
        result = migrator.migrate(payload)

        # The step metadata should note preserved keys
        all_meta = [s.get("metadata", {}) for s in result.report.applied_steps]
        all_changes = []
        for m in all_meta:
            all_changes.extend(m.get("changes", []))

        has_preserved = any("preserved" in c or "exotic_field" in c for c in all_changes)
        has_in_extras = "exotic_field" in result.payload.get("_extras", {})
        assert has_preserved or has_in_extras


# ===================================================================
# 3. Restored state matches migrated serialized state
# ===================================================================

class TestRestoredStateMatchesSerialized:
    """After migration, payload sections are well-formed."""

    def test_payload_sections_are_dicts(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())

        for section in (
            "coherence_core", "social_state_core", "campaign_memory_core",
            "arc_control_controller", "encounter_controller",
            "world_sim_controller", "recovery_manager", "creator_state",
        ):
            assert isinstance(result.payload.get(section), dict), (
                f"{section} should be a dict"
            )

    def test_encounter_world_arc_social_memory_present(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        p = result.payload

        assert "encounter_controller" in p
        assert "world_sim_controller" in p
        assert "arc_control_controller" in p
        assert "social_state_core" in p
        assert "campaign_memory_core" in p

    def test_pack_registry_well_formed_after_migration(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        pr = result.payload.get("pack_registry")

        assert isinstance(pr, dict)


# ===================================================================
# 4. Future-version saves fail clearly
# ===================================================================

class TestFutureVersionFails:
    """Payloads from the future are rejected with clear errors."""

    def test_future_save_version_fails(self):
        migrator = SaveMigrator()
        payload = {"save_format_version": CURRENT_SAVE_FORMAT_VERSION + 10}
        compat = migrator.check_compatibility(payload)

        assert compat.compatible is False
        assert any("newer" in e for e in compat.errors)

    def test_future_pack_version_fails(self):
        migrator = PackMigrator()
        pack = {"pack_format_version": CURRENT_PACK_FORMAT_VERSION + 10, "metadata": {}}
        compat = migrator.check_compatibility(pack)

        assert compat.compatible is False
        assert any("newer" in e for e in compat.errors)


# ===================================================================
# 5. Pack migration preserves deterministic ordering
# ===================================================================

class TestPackDeterministicOrdering:
    """Content and metadata keys are deterministically ordered."""

    def test_content_keys_deterministic_after_migration(self):
        migrator = PackMigrator()
        pack = _legacy_pack_payload()
        pack["content"]["z_module"] = {"data": 1}
        pack["content"]["a_module"] = {"data": 2}

        r1 = migrator.migrate(copy.deepcopy(pack))
        r2 = migrator.migrate(copy.deepcopy(pack))

        assert list(r1.payload["content"].keys()) == list(r2.payload["content"].keys())

    def test_multiple_pack_migrations_same_ordering(self):
        migrator = PackMigrator()
        pack = _legacy_pack_payload()
        pack["content"]["beta"] = {}
        pack["content"]["alpha"] = {}

        results = [
            migrator.migrate(copy.deepcopy(pack)) for _ in range(5)
        ]

        first_keys = list(results[0].payload["content"].keys())
        for r in results[1:]:
            assert list(r.payload["content"].keys()) == first_keys

    def test_metadata_fields_stable_ordering(self):
        migrator = PackMigrator()
        pack = _legacy_pack_payload()

        r1 = migrator.migrate(copy.deepcopy(pack))
        r2 = migrator.migrate(copy.deepcopy(pack))

        meta1 = r1.payload.get("metadata", {})
        meta2 = r2.payload.get("metadata", {})
        assert list(meta1.keys()) == list(meta2.keys())


# ===================================================================
# 6. Debug bundle can surface migration reports without mutation
# ===================================================================

class TestDebugBundleReports:
    """Migration reports serialize safely for debug bundles."""

    def test_report_serializes_to_dict(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        report_dict = result.report.to_dict()

        assert isinstance(report_dict, dict)
        assert "scope" in report_dict
        assert "applied_steps" in report_dict
        assert "errors" in report_dict
        assert "warnings" in report_dict

    def test_report_dict_is_independent_copy(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        report_dict = result.report.to_dict()

        # Mutate the copy — original must be unaffected
        report_dict["errors"].append("INJECTED_ERROR")
        report_dict["applied_steps"].clear()

        assert "INJECTED_ERROR" not in result.report.errors
        assert len(result.report.applied_steps) > 0

    def test_report_suitable_for_json_serialization(self):
        migrator = SaveMigrator()
        result = migrator.migrate(_legacy_save_payload())
        report_dict = result.report.to_dict()

        serialized = json.dumps(report_dict)
        deserialized = json.loads(serialized)
        assert deserialized == report_dict

    def test_pack_report_independent_from_last_report_cache(self):
        migrator = PackMigrator()
        migrator.migrate(_legacy_pack_payload())
        cached = migrator.get_last_report()

        assert cached is not None
        cached["errors"].append("INJECTED")

        # Re-fetch — should still be the mutated copy, but a fresh
        # migrate must produce a clean report.
        fresh = migrator.migrate(_legacy_pack_payload())
        assert "INJECTED" not in fresh.report.errors
