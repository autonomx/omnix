"""Comprehensive unit tests for Phase 8.5 — Save Migration / Packaging Interoperability.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_phase85_migration.py -v --noconftest
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.migration.models import (
    CURRENT_PACK_FORMAT_VERSION,
    CURRENT_SAVE_FORMAT_VERSION,
    SUPPORTED_MIGRATION_SCOPES,
    CompatibilityReport,
    MigratedPayload,
    MigrationReport,
    MigrationStep,
    PackCompatibilityResult,
)
from app.rpg.migration.registry import MigrationRegistry
from app.rpg.migration.save_migrator import SaveMigrator, build_default_registry
from app.rpg.migration.pack_migrator import PackMigrator, register_default_pack_steps


# ======================================================================
# Helpers — reusable factory data
# ======================================================================

def _make_legacy_save(**overrides) -> dict:
    """Build a minimal legacy (v0) save payload with no version stamp."""
    payload: dict = {
        "coherence_core": {"some": "data"},
        "social_state_core": {},
    }
    payload.update(overrides)
    return payload


def _make_v1_save(**overrides) -> dict:
    """Build a minimal v1 save payload."""
    payload: dict = {
        "save_format_version": 1,
        "coherence_core": {},
        "social_state_core": {},
        "campaign_memory_core": {},
        "arc_control_controller": {},
        "encounter_controller": {},
        "world_sim_controller": {},
        "pack_registry": {"packs": {}},
        "recovery_manager": {},
        "creator_state": {},
        "runtime_cache": {},
        "engine_metadata": {},
    }
    payload.update(overrides)
    return payload


def _make_v2_save(**overrides) -> dict:
    """Build a minimal v2 (current) save payload."""
    payload = _make_v1_save(save_format_version=2)
    payload.update(overrides)
    return payload


def _make_legacy_pack(**overrides) -> dict:
    """Build a minimal legacy (v0) pack payload."""
    payload: dict = {
        "metadata": {"pack_id": "demo-pack", "title": "Demo", "version": "0.1"},
        "content": {"scenes": []},
    }
    payload.update(overrides)
    return payload


def _make_v1_pack(**overrides) -> dict:
    """Build a minimal v1 pack payload."""
    payload: dict = {
        "pack_format_version": 1,
        "metadata": {"pack_id": "demo-pack", "title": "Demo", "version": "1.0"},
        "content": {},
        "manifest": {},
    }
    payload.update(overrides)
    return payload


def _make_v2_pack(**overrides) -> dict:
    """Build a minimal v2 (current) pack payload."""
    payload = _make_v1_pack(pack_format_version=2)
    payload["engine_compatibility"] = {}
    payload["dependencies"] = []
    payload.update(overrides)
    return payload


def _noop_step(payload: dict) -> tuple[dict, dict]:
    """No-op migration step for testing."""
    return dict(payload), {}


def _failing_step(payload: dict) -> tuple[dict, dict]:
    """Always-failing migration step for testing."""
    raise RuntimeError("intentional step failure")


# ======================================================================
# Model roundtrip tests
# ======================================================================


class TestMigrationStep:
    """Tests for MigrationStep model."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        step = MigrationStep(from_version=0, to_version=1, scope="save",
                             name="s01", description="d", metadata={"k": "v"})
        assert MigrationStep.from_dict(step.to_dict()) == step

    def test_to_dict_keys(self) -> None:
        step = MigrationStep(from_version=1, to_version=2, scope="pack")
        d = step.to_dict()
        assert set(d.keys()) == {
            "from_version", "to_version", "scope", "name", "description", "metadata",
        }

    def test_default_name_is_empty(self) -> None:
        step = MigrationStep(from_version=0, to_version=1, scope="save")
        assert step.name == ""

    def test_default_description_is_empty(self) -> None:
        step = MigrationStep(from_version=0, to_version=1, scope="save")
        assert step.description == ""

    def test_default_metadata_is_empty_dict(self) -> None:
        step = MigrationStep(from_version=0, to_version=1, scope="save")
        assert step.metadata == {}

    def test_from_dict_with_missing_keys_uses_defaults(self) -> None:
        step = MigrationStep.from_dict({})
        assert step.from_version == 0
        assert step.to_version == 0
        assert step.scope == ""
        assert step.name == ""

    def test_to_dict_returns_new_outer_dict(self) -> None:
        step = MigrationStep(from_version=0, to_version=1, scope="save", metadata={"k": "v"})
        d1 = step.to_dict()
        d2 = step.to_dict()
        assert d1 is not d2

    def test_roundtrip_preserves_scope(self) -> None:
        for scope in ("save", "pack"):
            step = MigrationStep(from_version=0, to_version=1, scope=scope)
            rebuilt = MigrationStep.from_dict(step.to_dict())
            assert rebuilt.scope == scope


class TestMigrationReport:
    """Tests for MigrationReport model."""

    def test_to_dict_from_dict_roundtrip_empty(self) -> None:
        report = MigrationReport()
        assert MigrationReport.from_dict(report.to_dict()) == report

    def test_to_dict_from_dict_roundtrip_populated(self) -> None:
        report = MigrationReport(
            scope="save", original_version=0, final_version=2,
            applied_steps=[{"name": "s01"}], warnings=["w1"],
            errors=["e1"], changed_keys=["ck"], metadata={"m": 1},
        )
        assert MigrationReport.from_dict(report.to_dict()) == report

    def test_default_lists_are_empty(self) -> None:
        report = MigrationReport()
        assert report.applied_steps == []
        assert report.warnings == []
        assert report.errors == []
        assert report.changed_keys == []

    def test_original_version_default_none(self) -> None:
        report = MigrationReport()
        assert report.original_version is None

    def test_final_version_default_none(self) -> None:
        report = MigrationReport()
        assert report.final_version is None

    def test_to_dict_contains_expected_keys(self) -> None:
        d = MigrationReport().to_dict()
        assert set(d.keys()) == {
            "scope", "original_version", "final_version",
            "applied_steps", "warnings", "errors", "changed_keys", "metadata",
        }


class TestCompatibilityReport:
    """Tests for CompatibilityReport model."""

    def test_roundtrip_empty(self) -> None:
        report = CompatibilityReport()
        assert CompatibilityReport.from_dict(report.to_dict()) == report

    def test_roundtrip_with_errors(self) -> None:
        report = CompatibilityReport(
            scope="pack", compatible=False, format_version=99,
            engine_constraints={"min": 1}, warnings=["w"],
            errors=["too new"], metadata={"x": 1},
        )
        assert CompatibilityReport.from_dict(report.to_dict()) == report

    def test_default_compatible_is_true(self) -> None:
        assert CompatibilityReport().compatible is True

    def test_default_format_version_is_none(self) -> None:
        assert CompatibilityReport().format_version is None


class TestMigratedPayload:
    """Tests for MigratedPayload model."""

    def test_roundtrip_empty(self) -> None:
        mp = MigratedPayload()
        assert MigratedPayload.from_dict(mp.to_dict()) == mp

    def test_roundtrip_with_data(self) -> None:
        mp = MigratedPayload(
            payload={"a": 1},
            report=MigrationReport(scope="save", original_version=0, final_version=2),
        )
        rebuilt = MigratedPayload.from_dict(mp.to_dict())
        assert rebuilt.payload == {"a": 1}
        assert rebuilt.report.scope == "save"

    def test_to_dict_keys(self) -> None:
        d = MigratedPayload().to_dict()
        assert set(d.keys()) == {"payload", "report"}


class TestPackCompatibilityResult:
    """Tests for PackCompatibilityResult model."""

    def test_roundtrip_empty(self) -> None:
        pcr = PackCompatibilityResult()
        assert PackCompatibilityResult.from_dict(pcr.to_dict()) == pcr

    def test_roundtrip_with_data(self) -> None:
        pcr = PackCompatibilityResult(
            pack_id="test-pack", compatible=False,
            normalized_pack={"metadata": {}},
            report=MigrationReport(scope="pack"),
        )
        rebuilt = PackCompatibilityResult.from_dict(pcr.to_dict())
        assert rebuilt.pack_id == "test-pack"
        assert rebuilt.compatible is False

    def test_default_compatible_is_true(self) -> None:
        assert PackCompatibilityResult().compatible is True

    def test_default_pack_id_is_none(self) -> None:
        assert PackCompatibilityResult().pack_id is None


class TestConstants:
    """Tests for module-level constants."""

    def test_current_save_format_version(self) -> None:
        assert CURRENT_SAVE_FORMAT_VERSION == 2

    def test_current_pack_format_version(self) -> None:
        assert CURRENT_PACK_FORMAT_VERSION == 2

    def test_supported_scopes_contains_save(self) -> None:
        assert "save" in SUPPORTED_MIGRATION_SCOPES

    def test_supported_scopes_contains_pack(self) -> None:
        assert "pack" in SUPPORTED_MIGRATION_SCOPES

    def test_supported_scopes_is_frozenset(self) -> None:
        assert isinstance(SUPPORTED_MIGRATION_SCOPES, frozenset)


# ======================================================================
# Registry tests
# ======================================================================


class TestMigrationRegistry:
    """Tests for MigrationRegistry."""

    def test_register_save_step_succeeds(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step, name="s01")

    def test_register_pack_step_succeeds(self) -> None:
        reg = MigrationRegistry()
        reg.register_pack_step(0, 1, _noop_step, name="p01")

    def test_reject_non_plus_one_save_hop(self) -> None:
        reg = MigrationRegistry()
        with pytest.raises(ValueError, match=r"Only \+1 version hops"):
            reg.register_save_step(0, 2, _noop_step)

    def test_reject_non_plus_one_pack_hop(self) -> None:
        reg = MigrationRegistry()
        with pytest.raises(ValueError, match=r"Only \+1 version hops"):
            reg.register_pack_step(0, 3, _noop_step)

    def test_reject_duplicate_save_registration(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step)
        with pytest.raises(ValueError, match="Duplicate"):
            reg.register_save_step(0, 1, _noop_step)

    def test_reject_duplicate_pack_registration(self) -> None:
        reg = MigrationRegistry()
        reg.register_pack_step(0, 1, _noop_step)
        with pytest.raises(ValueError, match="Duplicate"):
            reg.register_pack_step(0, 1, _noop_step)

    def test_get_save_path_returns_correct_steps(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step, name="s01")
        reg.register_save_step(1, 2, _noop_step, name="s12")
        path = reg.get_save_path(0, 2)
        assert len(path) == 2
        assert path[0].name == "s01"
        assert path[1].name == "s12"

    def test_get_pack_path_returns_correct_steps(self) -> None:
        reg = MigrationRegistry()
        reg.register_pack_step(0, 1, _noop_step, name="p01")
        path = reg.get_pack_path(0, 1)
        assert len(path) == 1
        assert path[0].name == "p01"

    def test_get_save_path_empty_for_gap(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step)
        # Missing 1->2 step, so path 0->2 has a gap
        assert reg.get_save_path(0, 2) == []

    def test_has_path_true_for_existing(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step)
        assert reg.has_path("save", 0, 1) is True

    def test_has_path_false_for_missing(self) -> None:
        reg = MigrationRegistry()
        assert reg.has_path("save", 0, 1) is False

    def test_has_path_true_when_from_equals_to(self) -> None:
        reg = MigrationRegistry()
        assert reg.has_path("save", 2, 2) is True

    def test_has_path_false_for_unsupported_scope(self) -> None:
        reg = MigrationRegistry()
        assert reg.has_path("invalid", 0, 1) is False

    def test_has_path_false_when_from_greater_than_to(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step)
        assert reg.has_path("save", 1, 0) is False

    def test_migrate_save_path_correctly(self) -> None:
        reg = MigrationRegistry()

        def step_fn(p: dict) -> tuple[dict, dict]:
            out = dict(p)
            out["migrated"] = True
            return out, {"did": "migrate"}

        reg.register_save_step(0, 1, step_fn, name="s01")
        result = reg.migrate("save", {"data": 1}, 0, 1)
        assert result.payload.get("migrated") is True
        assert len(result.report.applied_steps) == 1

    def test_migrate_pack_path_correctly(self) -> None:
        reg = MigrationRegistry()
        reg.register_pack_step(0, 1, _noop_step, name="p01")
        result = reg.migrate("pack", {}, 0, 1)
        assert not result.report.errors
        assert len(result.report.applied_steps) == 1

    def test_migrate_reports_errors_for_missing_path(self) -> None:
        reg = MigrationRegistry()
        result = reg.migrate("save", {}, 0, 1)
        assert len(result.report.errors) > 0
        assert "No migration step" in result.report.errors[0]

    def test_migrate_handles_from_equals_to(self) -> None:
        reg = MigrationRegistry()
        result = reg.migrate("save", {"x": 1}, 2, 2)
        assert result.payload == {"x": 1}
        assert not result.report.errors
        assert result.report.final_version == 2

    def test_migrate_rejects_downgrade(self) -> None:
        reg = MigrationRegistry()
        result = reg.migrate("save", {}, 2, 1)
        assert len(result.report.errors) > 0
        assert "Downgrade" in result.report.errors[0]

    def test_migrate_rejects_unsupported_scope(self) -> None:
        reg = MigrationRegistry()
        result = reg.migrate("invalid_scope", {}, 0, 1)
        assert len(result.report.errors) > 0
        assert "Unsupported" in result.report.errors[0]

    def test_migrate_collects_changed_keys(self) -> None:
        reg = MigrationRegistry()

        def add_key(p: dict) -> tuple[dict, dict]:
            out = dict(p)
            out["new_key"] = True
            return out, {}

        reg.register_save_step(0, 1, add_key, name="s01")
        result = reg.migrate("save", {}, 0, 1)
        assert "new_key" in result.report.changed_keys

    def test_migrate_collects_applied_steps(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _noop_step, name="step_alpha")
        reg.register_save_step(1, 2, _noop_step, name="step_beta")
        result = reg.migrate("save", {}, 0, 2)
        names = [s["name"] for s in result.report.applied_steps]
        assert names == ["step_alpha", "step_beta"]

    def test_migrate_handles_step_exception_gracefully(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _failing_step, name="bad_step")
        result = reg.migrate("save", {"original": True}, 0, 1)
        assert len(result.report.errors) > 0
        assert "bad_step" in result.report.errors[0]
        assert "intentional step failure" in result.report.errors[0]
        # Payload should remain unchanged since the step failed
        assert result.payload.get("original") is True

    def test_migrate_stops_at_failed_step(self) -> None:
        reg = MigrationRegistry()
        reg.register_save_step(0, 1, _failing_step, name="fail_01")
        reg.register_save_step(1, 2, _noop_step, name="ok_12")
        result = reg.migrate("save", {}, 0, 2)
        assert result.report.final_version == 0
        assert len(result.report.applied_steps) == 0


# ======================================================================
# SaveMigrator tests
# ======================================================================


class TestSaveMigrator:
    """Tests for SaveMigrator."""

    def test_detect_version_from_explicit_field(self) -> None:
        m = SaveMigrator()
        assert m.detect_version({"save_format_version": 2}) == 2

    def test_detect_version_infers_zero_from_legacy(self) -> None:
        m = SaveMigrator()
        assert m.detect_version({"coherence_core": {}}) == 0

    def test_detect_version_returns_none_for_empty(self) -> None:
        m = SaveMigrator()
        assert m.detect_version({}) is None

    def test_detect_version_coerces_string_to_int(self) -> None:
        m = SaveMigrator()
        assert m.detect_version({"save_format_version": "1"}) == 1

    def test_check_compatibility_current_version(self) -> None:
        m = SaveMigrator()
        report = m.check_compatibility(_make_v2_save())
        assert report.compatible is True
        assert report.format_version == CURRENT_SAVE_FORMAT_VERSION

    def test_check_compatibility_legacy_v0(self) -> None:
        m = SaveMigrator()
        report = m.check_compatibility(_make_legacy_save())
        assert report.compatible is True
        assert report.format_version == 0

    def test_check_compatibility_rejects_future_version(self) -> None:
        m = SaveMigrator()
        report = m.check_compatibility({"save_format_version": 999})
        assert report.compatible is False
        assert len(report.errors) > 0
        assert "newer" in report.errors[0]

    def test_check_compatibility_rejects_empty(self) -> None:
        m = SaveMigrator()
        report = m.check_compatibility({})
        assert report.compatible is False
        assert "Empty" in report.errors[0]

    def test_check_compatibility_rejects_no_migration_path(self) -> None:
        empty_reg = MigrationRegistry()
        m = SaveMigrator(registry=empty_reg)
        report = m.check_compatibility(_make_legacy_save())
        assert report.compatible is False
        assert "No migration path" in report.errors[0]

    def test_normalize_payload_fills_missing_sections(self) -> None:
        m = SaveMigrator()
        result = m.normalize_payload({})
        for section in ("coherence_core", "social_state_core", "pack_registry",
                        "recovery_manager", "creator_state"):
            assert section in result
            assert isinstance(result[section], dict)

    def test_normalize_payload_preserves_existing_sections(self) -> None:
        m = SaveMigrator()
        payload = {"coherence_core": {"existing": "data"}}
        result = m.normalize_payload(payload)
        assert result["coherence_core"] == {"existing": "data"}

    def test_normalize_payload_adds_runtime_cache(self) -> None:
        m = SaveMigrator()
        result = m.normalize_payload({})
        assert "runtime_cache" in result
        assert isinstance(result["runtime_cache"], dict)
        assert "last_dialogue_response" in result["runtime_cache"]

    def test_normalize_payload_adds_engine_metadata(self) -> None:
        m = SaveMigrator()
        result = m.normalize_payload({})
        assert "engine_metadata" in result

    def test_normalize_payload_preserves_existing_engine_metadata(self) -> None:
        m = SaveMigrator()
        result = m.normalize_payload({"engine_metadata": {"ver": 3}})
        assert result["engine_metadata"] == {"ver": 3}

    def test_migrate_from_0_to_current_succeeds(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save())
        assert not result.report.errors
        assert result.payload.get("save_format_version") == CURRENT_SAVE_FORMAT_VERSION

    def test_migrate_from_1_to_current_succeeds(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_v1_save())
        assert not result.report.errors
        assert result.payload.get("save_format_version") == CURRENT_SAVE_FORMAT_VERSION

    def test_migrate_stamps_final_version(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save())
        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION

    def test_migrate_handles_empty_payload(self) -> None:
        m = SaveMigrator()
        result = m.migrate({})
        assert result.report.errors
        assert "Empty" in result.report.errors[0]

    def test_migrate_already_at_current_is_noop(self) -> None:
        m = SaveMigrator()
        payload = _make_v2_save()
        result = m.migrate(payload)
        assert result.payload["save_format_version"] == CURRENT_SAVE_FORMAT_VERSION
        assert not result.report.errors
        assert result.report.applied_steps == []

    def test_migrate_0_to_1_adds_save_format_version(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save(), target_version=1)
        assert result.payload.get("save_format_version") == 1

    def test_migrate_0_to_1_normalizes_missing_containers(self) -> None:
        m = SaveMigrator()
        result = m.migrate({"some_legacy_key": "val"}, target_version=1)
        for section in ("encounter_controller", "world_sim_controller"):
            assert section in result.payload

    def test_migrate_0_to_1_renames_legacy_packs_key(self) -> None:
        m = SaveMigrator()
        payload = {"packs": {"old_pack": {}}}
        result = m.migrate(payload, target_version=1)
        # normalize_payload adds pack_registry before step runs, so the
        # step sees both "packs" and "pack_registry" — legacy packs are
        # preserved in _extras.
        extras = result.payload.get("_extras", {})
        assert extras.get("legacy_packs") == {"old_pack": {}}

    def test_migrate_1_to_2_adds_runtime_cache(self) -> None:
        m = SaveMigrator()
        v1 = _make_v1_save()
        del v1["runtime_cache"]
        result = m.migrate(v1, target_version=2)
        assert "runtime_cache" in result.payload
        assert isinstance(result.payload["runtime_cache"], dict)

    def test_migrate_1_to_2_normalizes_pack_registry(self) -> None:
        m = SaveMigrator()
        v1 = _make_v1_save(pack_registry={"some_pack": {}})
        result = m.migrate(v1, target_version=2)
        pr = result.payload.get("pack_registry")
        assert isinstance(pr, dict)
        # Should be wrapped in {"packs": ...} form
        assert "packs" in pr

    def test_migrate_1_to_2_preserves_unknown_keys_in_extras(self) -> None:
        m = SaveMigrator()
        v1 = _make_v1_save(custom_field="hello")
        result = m.migrate(v1, target_version=2)
        extras = result.payload.get("_extras", {})
        assert extras.get("custom_field") == "hello"

    def test_migrate_1_to_2_adds_engine_metadata(self) -> None:
        m = SaveMigrator()
        v1 = _make_v1_save()
        del v1["engine_metadata"]
        result = m.migrate(v1, target_version=2)
        assert "engine_metadata" in result.payload

    def test_build_default_registry_returns_working_registry(self) -> None:
        reg = build_default_registry()
        assert reg.has_path("save", 0, CURRENT_SAVE_FORMAT_VERSION)
        assert reg.has_path("pack", 0, CURRENT_PACK_FORMAT_VERSION)

    def test_migrate_does_not_mutate_original(self) -> None:
        m = SaveMigrator()
        original = _make_legacy_save()
        frozen = copy.deepcopy(original)
        m.migrate(original)
        assert original == frozen

    def test_migrate_report_has_scope_save(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save())
        assert result.report.scope == "save"

    def test_migrate_report_original_version_set(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save())
        assert result.report.original_version == 0

    def test_migrate_report_final_version_set(self) -> None:
        m = SaveMigrator()
        result = m.migrate(_make_legacy_save())
        assert result.report.final_version == CURRENT_SAVE_FORMAT_VERSION


# ======================================================================
# PackMigrator tests
# ======================================================================


class TestPackMigrator:
    """Tests for PackMigrator."""

    def test_detect_version_from_explicit_field(self) -> None:
        m = PackMigrator()
        assert m.detect_version({"pack_format_version": 2}) == 2

    def test_detect_version_infers_zero_from_legacy_with_metadata(self) -> None:
        m = PackMigrator()
        assert m.detect_version({"metadata": {"pack_id": "x"}}) == 0

    def test_detect_version_infers_zero_from_legacy_with_content(self) -> None:
        m = PackMigrator()
        assert m.detect_version({"content": {"scenes": []}}) == 0

    def test_detect_version_returns_none_for_empty(self) -> None:
        m = PackMigrator()
        assert m.detect_version({}) is None

    def test_detect_version_coerces_string_to_int(self) -> None:
        m = PackMigrator()
        assert m.detect_version({"pack_format_version": "1"}) == 1

    def test_check_compatibility_current_version(self) -> None:
        m = PackMigrator()
        report = m.check_compatibility(_make_v2_pack())
        assert report.compatible is True

    def test_check_compatibility_rejects_future_version(self) -> None:
        m = PackMigrator()
        report = m.check_compatibility({"pack_format_version": 999, "metadata": {}})
        assert report.compatible is False
        assert "newer" in report.errors[0]

    def test_check_compatibility_rejects_empty(self) -> None:
        m = PackMigrator()
        report = m.check_compatibility({})
        assert report.compatible is False
        assert "Empty" in report.errors[0]

    def test_check_compatibility_engine_min_save_version(self) -> None:
        m = PackMigrator()
        pack = _make_v2_pack(engine_compatibility={"min_save_format_version": 999})
        report = m.check_compatibility(pack)
        assert report.compatible is False
        assert any("min_save_format_version" in e for e in report.errors)

    def test_check_compatibility_engine_max_save_version(self) -> None:
        m = PackMigrator()
        pack = _make_v2_pack(engine_compatibility={"max_save_format_version": 0})
        report = m.check_compatibility(pack)
        assert report.compatible is False
        assert any("max_save_format_version" in e for e in report.errors)

    def test_check_compatibility_engine_constraints_within_range(self) -> None:
        m = PackMigrator()
        pack = _make_v2_pack(engine_compatibility={
            "min_save_format_version": 0,
            "max_save_format_version": 99,
        })
        report = m.check_compatibility(pack)
        assert report.compatible is True

    def test_normalize_pack_fills_missing_metadata_fields(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({})
        assert "metadata" in result
        assert result["metadata"]["pack_id"] == ""
        assert result["metadata"]["title"] == ""
        assert result["metadata"]["version"] == ""

    def test_normalize_pack_fills_missing_content(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({})
        assert "content" in result
        assert isinstance(result["content"], dict)

    def test_normalize_pack_fills_missing_manifest(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({})
        assert "manifest" in result
        assert isinstance(result["manifest"], dict)

    def test_normalize_pack_fills_engine_compatibility(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({})
        assert "engine_compatibility" in result

    def test_normalize_pack_fills_dependencies(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({})
        assert "dependencies" in result
        assert isinstance(result["dependencies"], list)

    def test_normalize_pack_preserves_existing_metadata(self) -> None:
        m = PackMigrator()
        result = m.normalize_pack({"metadata": {"pack_id": "my-pack", "custom": "x"}})
        assert result["metadata"]["pack_id"] == "my-pack"
        assert result["metadata"]["custom"] == "x"

    def test_validate_pack_structure_detects_missing_metadata(self) -> None:
        m = PackMigrator()
        issues = m.validate_pack_structure({"content": {}})
        assert any("metadata" in i for i in issues)

    def test_validate_pack_structure_detects_missing_pack_id(self) -> None:
        m = PackMigrator()
        issues = m.validate_pack_structure({"metadata": {"title": "T"}, "content": {}})
        assert any("pack_id" in i for i in issues)

    def test_validate_pack_structure_detects_missing_version_stamp(self) -> None:
        m = PackMigrator()
        issues = m.validate_pack_structure({"metadata": {"pack_id": "x"}, "content": {}})
        assert any("pack_format_version" in i for i in issues)

    def test_validate_pack_structure_no_issues_for_complete_pack(self) -> None:
        m = PackMigrator()
        pack = _make_v2_pack()
        issues = m.validate_pack_structure(pack)
        # Should only have non-error issues or none at all
        errors = [i for i in issues if i.startswith("error:")]
        assert len(errors) == 0

    def test_migrate_0_to_1_adds_version_and_normalizes(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_legacy_pack(), target_version=1)
        assert result.payload.get("pack_format_version") == 1
        assert "metadata" in result.payload
        assert "content" in result.payload

    def test_migrate_1_to_2_adds_engine_compatibility(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_v1_pack(), target_version=2)
        assert "engine_compatibility" in result.payload
        assert result.payload.get("pack_format_version") == 2

    def test_migrate_1_to_2_preserves_unknown_keys(self) -> None:
        m = PackMigrator()
        v1 = _make_v1_pack(custom_extension="data")
        result = m.migrate(v1, target_version=2)
        extras = result.payload.get("_extras", {})
        assert extras.get("custom_extension") == "data"

    def test_migrate_handles_empty_payload(self) -> None:
        m = PackMigrator()
        result = m.migrate({})
        assert result.report.errors
        assert "Empty" in result.report.errors[0]

    def test_migrate_already_at_current_is_noop(self) -> None:
        m = PackMigrator()
        pack = _make_v2_pack()
        result = m.migrate(pack)
        assert result.payload.get("pack_format_version") == CURRENT_PACK_FORMAT_VERSION
        assert not result.report.errors
        assert result.report.applied_steps == []

    def test_get_last_report_returns_none_initially(self) -> None:
        m = PackMigrator()
        assert m.get_last_report() is None

    def test_get_last_report_returns_report_after_migration(self) -> None:
        m = PackMigrator()
        m.migrate(_make_legacy_pack())
        report = m.get_last_report()
        assert report is not None
        assert isinstance(report, dict)
        assert "scope" in report

    def test_migrate_does_not_mutate_original(self) -> None:
        m = PackMigrator()
        original = _make_legacy_pack()
        frozen = copy.deepcopy(original)
        m.migrate(original)
        assert original == frozen

    def test_migrate_0_to_current_succeeds(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_legacy_pack())
        assert not result.report.errors
        assert result.payload.get("pack_format_version") == CURRENT_PACK_FORMAT_VERSION

    def test_migrate_report_has_scope_pack(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_legacy_pack())
        assert result.report.scope == "pack"

    def test_migrate_report_original_version_set(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_legacy_pack())
        assert result.report.original_version == 0

    def test_migrate_report_final_version_set(self) -> None:
        m = PackMigrator()
        result = m.migrate(_make_legacy_pack())
        assert result.report.final_version == CURRENT_PACK_FORMAT_VERSION

    def test_migrate_1_to_2_adds_dependencies(self) -> None:
        m = PackMigrator()
        v1 = _make_v1_pack()
        result = m.migrate(v1, target_version=2)
        assert "dependencies" in result.payload
        assert isinstance(result.payload["dependencies"], list)
