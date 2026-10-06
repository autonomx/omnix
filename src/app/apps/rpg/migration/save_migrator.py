"""Phase 8.5 — Save Migrator.

Main entry point for save/snapshot migration.
Normalizes, detects versions, and migrates serialized save payloads
before they are used to reconstruct live controller state.
"""

from __future__ import annotations

import copy
from typing import Any

from .models import (
    CURRENT_SAVE_FORMAT_VERSION,
    CompatibilityReport,
    MigratedPayload,
    MigrationReport,
)
from .registry import MigrationRegistry

# Top-level sections expected in a current-format save payload.
_AUTHORITATIVE_SECTIONS: frozenset[str] = frozenset({
    "coherence_core",
    "social_state_core",
    "campaign_memory_core",
    "arc_control_controller",
    "encounter_controller",
    "world_sim_controller",
    "pack_registry",
    "recovery_manager",
    "creator_state",
})

# Derived / runtime cache sections that may be safely reset.
_RUNTIME_CACHE_KEYS: frozenset[str] = frozenset({
    "last_dialogue_response",
    "last_world_sim_result",
    "last_debug_bundle",
    "last_dialogue_trace",
    "last_control_output",
    "last_action_result",
    "last_encounter_resolution",
})


class SaveMigrator:
    """Migrate serialized save payloads to the current format version.

    Operates entirely on dicts — never touches live engine state.
    """

    def __init__(self, registry: MigrationRegistry | None = None) -> None:
        self._registry = registry or build_default_registry()

    # ------------------------------------------------------------------
    # Version detection
    # ------------------------------------------------------------------

    def detect_version(self, payload: dict[str, Any]) -> int | None:
        """Detect the save format version of *payload*.

        Returns ``None`` only when the payload is empty or completely
        unrecognisable.  Legacy saves without an explicit version are
        inferred as version ``0``.
        """
        if not payload:
            return None
        version = payload.get("save_format_version")
        if version is not None:
            return int(version)
        # Heuristic: any non-empty dict without a version stamp is legacy v0.
        return 0

    # ------------------------------------------------------------------
    # Compatibility check
    # ------------------------------------------------------------------

    def check_compatibility(self, payload: dict[str, Any]) -> CompatibilityReport:
        """Check whether *payload* can be migrated to the current version."""
        report = CompatibilityReport(scope="save")
        version = self.detect_version(payload)
        report.format_version = version

        if version is None:
            report.compatible = False
            report.errors.append("Empty or unrecognisable save payload")
            return report

        if version > CURRENT_SAVE_FORMAT_VERSION:
            report.compatible = False
            report.errors.append(
                f"Save version {version} is newer than supported "
                f"({CURRENT_SAVE_FORMAT_VERSION}); no downgrade path exists"
            )
            return report

        if version < CURRENT_SAVE_FORMAT_VERSION:
            if not self._registry.has_path("save", version, CURRENT_SAVE_FORMAT_VERSION):
                report.compatible = False
                report.errors.append(
                    f"No migration path from version {version} to "
                    f"{CURRENT_SAVE_FORMAT_VERSION}"
                )
                return report

        # Check required top-level shape (only for current-version saves).
        if version == CURRENT_SAVE_FORMAT_VERSION:
            if not isinstance(payload, dict):
                report.compatible = False
                report.errors.append("Save payload is not a dict")
                return report

        report.compatible = True
        return report

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Conservative normalization before migration.

        Ensures top-level dict shape exists, fills missing sections with
        explicit defaults where safe, and reports any derived caches that
        were dropped.
        """
        out = dict(payload)

        # Ensure authoritative section containers exist (empty dict default).
        for key in _AUTHORITATIVE_SECTIONS:
            if key not in out:
                out[key] = {}

        # Ensure runtime_cache container exists.
        if "runtime_cache" not in out:
            out["runtime_cache"] = {}
        cache = out["runtime_cache"]
        for cache_key in _RUNTIME_CACHE_KEYS:
            cache.setdefault(cache_key, None)

        # Ensure engine_metadata container.
        out.setdefault("engine_metadata", {})

        return out

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate(
        self,
        payload: dict[str, Any],
        target_version: int | None = None,
    ) -> MigratedPayload:
        """Normalize, detect version, migrate, and stamp the result.

        If *target_version* is ``None``, migrates to
        ``CURRENT_SAVE_FORMAT_VERSION``.
        """
        target = target_version if target_version is not None else CURRENT_SAVE_FORMAT_VERSION
        working = copy.deepcopy(payload)

        # Detect
        version = self.detect_version(working)
        if version is None:
            report = MigrationReport(
                scope="save",
                original_version=None,
                final_version=None,
                errors=["Empty or unrecognisable save payload"],
            )
            return MigratedPayload(payload=working, report=report)

        # Normalize before migration
        working = self.normalize_payload(working)

        # Already at target?
        if version == target:
            working["save_format_version"] = target
            report = MigrationReport(
                scope="save",
                original_version=version,
                final_version=target,
            )
            return MigratedPayload(payload=working, report=report)

        # Migrate through registry
        result = self._registry.migrate("save", working, version, target)

        # Stamp final version
        result.payload["save_format_version"] = target if not result.report.errors else version

        return result


# ======================================================================
# Default migration steps
# ======================================================================

def _save_step_0_to_1(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Legacy/no-version saves → version 1.

    * Adds ``save_format_version = 1``
    * Normalizes missing top-level containers
    * Initializes absent encounter_controller / world_sim_controller
    * Renames obvious legacy keys if present
    """
    meta: dict[str, Any] = {"changes": []}
    out = dict(payload)

    out["save_format_version"] = 1

    # Ensure authoritative sections
    for key in sorted(_AUTHORITATIVE_SECTIONS):
        if key not in out:
            out[key] = {}
            meta["changes"].append(f"added_default:{key}")

    # Ensure engine_metadata
    if "engine_metadata" not in out:
        out["engine_metadata"] = {}
        meta["changes"].append("added_default:engine_metadata")

    # Legacy key renames (example: old "packs" -> "pack_registry")
    if "packs" in out and "pack_registry" not in out:
        out["pack_registry"] = out.pop("packs")
        meta["changes"].append("renamed:packs->pack_registry")
    elif "packs" in out:
        # Preserve under extras if both exist
        out.setdefault("_extras", {})["legacy_packs"] = out.pop("packs")
        meta["changes"].append("preserved:legacy_packs_in_extras")

    # Ensure runtime_cache
    if "runtime_cache" not in out:
        out["runtime_cache"] = {k: None for k in sorted(_RUNTIME_CACHE_KEYS)}
        meta["changes"].append("added_default:runtime_cache")

    return out, meta


def _save_step_1_to_2(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Post-encounter/world-sim era → version 2.

    * Adds explicit runtime_cache container if missing
    * Normalizes pack_registry shape
    * Adds or normalizes debug-related optional caches
    * Ensures engine_metadata exists
    """
    meta: dict[str, Any] = {"changes": []}
    out = dict(payload)

    out["save_format_version"] = 2

    # Ensure runtime_cache
    if "runtime_cache" not in out or not isinstance(out.get("runtime_cache"), dict):
        out["runtime_cache"] = {}
        meta["changes"].append("added_default:runtime_cache")
    cache = out["runtime_cache"]
    for cache_key in sorted(_RUNTIME_CACHE_KEYS):
        if cache_key not in cache:
            cache[cache_key] = None
            meta["changes"].append(f"added_cache_key:{cache_key}")

    # Normalize pack_registry: ensure it's a dict with "packs" key
    pr = out.get("pack_registry")
    if isinstance(pr, dict) and "packs" not in pr:
        # Might be a flat pack dict; wrap it
        if pr:
            out["pack_registry"] = {"packs": pr}
            meta["changes"].append("normalized:pack_registry_wrapped")
    elif pr is None or not isinstance(pr, dict):
        out["pack_registry"] = {"packs": {}}
        meta["changes"].append("added_default:pack_registry")

    # Ensure engine_metadata
    if "engine_metadata" not in out or not isinstance(out.get("engine_metadata"), dict):
        out["engine_metadata"] = {}
        meta["changes"].append("added_default:engine_metadata")

    # Preserve unknown top-level keys in _extras with warning
    known_keys = (
        _AUTHORITATIVE_SECTIONS
        | _RUNTIME_CACHE_KEYS
        | {"save_format_version", "engine_metadata", "runtime_cache", "_extras"}
    )
    unknown = sorted(set(out.keys()) - known_keys)
    if unknown:
        extras = out.setdefault("_extras", {})
        for uk in unknown:
            if uk.startswith("_"):
                continue
            extras[uk] = out[uk]
        meta["changes"].append(f"preserved_unknown_keys:{','.join(unknown)}")

    return out, meta


def build_default_registry() -> MigrationRegistry:
    """Build and return a :class:`MigrationRegistry` with default steps."""
    reg = MigrationRegistry()
    reg.register_save_step(
        0, 1, _save_step_0_to_1,
        name="save_0_to_1",
        description="Legacy saves: add version stamp and normalize containers",
    )
    reg.register_save_step(
        1, 2, _save_step_1_to_2,
        name="save_1_to_2",
        description="Add runtime cache, normalize pack registry, ensure engine metadata",
    )

    # Pack steps are registered by pack_migrator; import and register here
    # to keep a single combined registry available.
    from .pack_migrator import register_default_pack_steps
    register_default_pack_steps(reg)

    return reg
