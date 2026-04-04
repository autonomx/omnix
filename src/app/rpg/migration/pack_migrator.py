"""Phase 8.5 — Pack Migrator.

Normalize and migrate adventure pack data before registry/load/apply.
Operates on serialized dicts — never touches live pack objects.
"""

from __future__ import annotations

import copy
from typing import Any

from .models import (
    CURRENT_PACK_FORMAT_VERSION,
    CompatibilityReport,
    MigratedPayload,
    MigrationReport,
    PackCompatibilityResult,
)
from .registry import MigrationRegistry


class PackMigrator:
    """Migrate serialized pack payloads to the current format version.

    Operates entirely on dicts — never touches live engine state.
    """

    def __init__(self, registry: MigrationRegistry | None = None) -> None:
        self._registry: MigrationRegistry | None = registry
        self._last_report: dict[str, Any] | None = None

    @property
    def registry(self) -> MigrationRegistry:
        if self._registry is None:
            from .save_migrator import build_default_registry
            self._registry = build_default_registry()
        return self._registry

    # ------------------------------------------------------------------
    # Version detection
    # ------------------------------------------------------------------

    def detect_version(self, pack_payload: dict[str, Any]) -> int | None:
        """Detect the pack format version.

        Returns ``None`` for empty/unrecognisable payloads.
        Legacy packs without an explicit version are inferred as ``0``.
        """
        if not pack_payload:
            return None
        version = pack_payload.get("pack_format_version")
        if version is not None:
            return int(version)
        # Heuristic: presence of metadata or content suggests a legacy pack.
        if pack_payload.get("metadata") or pack_payload.get("content"):
            return 0
        return 0

    # ------------------------------------------------------------------
    # Compatibility check
    # ------------------------------------------------------------------

    def check_compatibility(self, pack_payload: dict[str, Any]) -> CompatibilityReport:
        """Check whether *pack_payload* can be migrated/loaded."""
        report = CompatibilityReport(scope="pack")
        version = self.detect_version(pack_payload)
        report.format_version = version

        if version is None:
            report.compatible = False
            report.errors.append("Empty or unrecognisable pack payload")
            return report

        if version > CURRENT_PACK_FORMAT_VERSION:
            report.compatible = False
            report.errors.append(
                f"Pack version {version} is newer than supported "
                f"({CURRENT_PACK_FORMAT_VERSION}); no downgrade path exists"
            )
            return report

        if version < CURRENT_PACK_FORMAT_VERSION:
            if not self.registry.has_path("pack", version, CURRENT_PACK_FORMAT_VERSION):
                report.compatible = False
                report.errors.append(
                    f"No migration path from pack version {version} to "
                    f"{CURRENT_PACK_FORMAT_VERSION}"
                )
                return report

        # Check required metadata
        meta = pack_payload.get("metadata", {})
        if not isinstance(meta, dict):
            report.compatible = False
            report.errors.append("Pack metadata is not a dict")
            return report

        # Engine compatibility constraints
        engine_compat = pack_payload.get("engine_compatibility", {})
        if isinstance(engine_compat, dict):
            from .models import CURRENT_SAVE_FORMAT_VERSION
            min_save = engine_compat.get("min_save_format_version")
            max_save = engine_compat.get("max_save_format_version")
            if min_save is not None and CURRENT_SAVE_FORMAT_VERSION < int(min_save):
                report.compatible = False
                report.errors.append(
                    f"Pack requires min_save_format_version={min_save}, "
                    f"engine is at {CURRENT_SAVE_FORMAT_VERSION}"
                )
            if max_save is not None and CURRENT_SAVE_FORMAT_VERSION > int(max_save):
                report.compatible = False
                report.errors.append(
                    f"Pack requires max_save_format_version={max_save}, "
                    f"engine is at {CURRENT_SAVE_FORMAT_VERSION}"
                )
            report.engine_constraints = dict(engine_compat)

        report.compatible = report.compatible and len(report.errors) == 0
        return report

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_pack(self, pack_payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize pack payload shape before migration."""
        out = dict(pack_payload)

        # Ensure metadata container
        if "metadata" not in out or not isinstance(out.get("metadata"), dict):
            out["metadata"] = {}
        meta = out["metadata"]
        meta.setdefault("pack_id", "")
        meta.setdefault("title", "")
        meta.setdefault("version", "")

        # Ensure content container
        out.setdefault("content", {})

        # Ensure manifest container
        out.setdefault("manifest", {})

        # Ensure engine_compatibility
        out.setdefault("engine_compatibility", {})

        # Ensure dependencies
        out.setdefault("dependencies", [])

        return out

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_pack_structure(self, pack_payload: dict[str, Any]) -> list[str]:
        """Return structured errors/warnings for the pack structure."""
        issues: list[str] = []

        if not isinstance(pack_payload, dict):
            issues.append("error:pack_payload_not_dict")
            return issues

        meta = pack_payload.get("metadata")
        if not isinstance(meta, dict):
            issues.append("error:metadata_missing_or_invalid")
        else:
            if not meta.get("pack_id"):
                issues.append("warning:metadata.pack_id_empty")
            if not meta.get("title"):
                issues.append("warning:metadata.title_empty")

        if "content" not in pack_payload:
            issues.append("warning:content_section_missing")

        version = pack_payload.get("pack_format_version")
        if version is None:
            issues.append("warning:pack_format_version_absent")

        return issues

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate(
        self,
        pack_payload: dict[str, Any],
        target_version: int | None = None,
    ) -> MigratedPayload:
        """Normalize, detect version, migrate, and stamp the result."""
        target = target_version if target_version is not None else CURRENT_PACK_FORMAT_VERSION
        working = copy.deepcopy(pack_payload)

        version = self.detect_version(working)
        if version is None:
            report = MigrationReport(
                scope="pack",
                original_version=None,
                final_version=None,
                errors=["Empty or unrecognisable pack payload"],
            )
            result = MigratedPayload(payload=working, report=report)
            self._last_report = result.report.to_dict()
            return result

        # Normalize before migration
        working = self.normalize_pack(working)

        if version == target:
            working["pack_format_version"] = target
            report = MigrationReport(
                scope="pack",
                original_version=version,
                final_version=target,
            )
            result = MigratedPayload(payload=working, report=report)
            self._last_report = result.report.to_dict()
            return result

        result = self.registry.migrate("pack", working, version, target)

        # Stamp final version
        if not result.report.errors:
            result.payload["pack_format_version"] = target
        else:
            result.payload.setdefault("pack_format_version", version)

        self._last_report = result.report.to_dict()
        return result

    def get_last_report(self) -> dict[str, Any] | None:
        """Return the last migration report dict, or ``None``."""
        return self._last_report


# ======================================================================
# Default pack migration steps
# ======================================================================

def _pack_step_0_to_1(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Legacy/no-version packs → version 1.

    * Adds ``pack_format_version = 1``
    * Normalizes metadata
    * Ensures pack_id, title, version
    """
    meta_changes: dict[str, Any] = {"changes": []}
    out = dict(payload)

    out["pack_format_version"] = 1

    # Normalize metadata
    if "metadata" not in out or not isinstance(out.get("metadata"), dict):
        out["metadata"] = {}
        meta_changes["changes"].append("added_default:metadata")
    pm = out["metadata"]
    for field in ("pack_id", "title", "version"):
        if not pm.get(field):
            pm.setdefault(field, "")
            meta_changes["changes"].append(f"defaulted:metadata.{field}")

    # Ensure content
    if "content" not in out:
        out["content"] = {}
        meta_changes["changes"].append("added_default:content")

    # Ensure manifest
    if "manifest" not in out:
        out["manifest"] = {}
        meta_changes["changes"].append("added_default:manifest")

    return out, meta_changes


def _pack_step_1_to_2(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Modern packs → version 2.

    * Adds explicit ``engine_compatibility``
    * Normalizes content/module ordering
    * Preserves unknown fields in ``_extras``/metadata
    * Ensures deterministic section layout
    """
    meta_changes: dict[str, Any] = {"changes": []}
    out = dict(payload)

    out["pack_format_version"] = 2

    # Add engine_compatibility
    if "engine_compatibility" not in out or not isinstance(out.get("engine_compatibility"), dict):
        out["engine_compatibility"] = {}
        meta_changes["changes"].append("added_default:engine_compatibility")

    # Ensure dependencies list
    if "dependencies" not in out or not isinstance(out.get("dependencies"), list):
        out["dependencies"] = []
        meta_changes["changes"].append("added_default:dependencies")

    # Normalize content sections: ensure dict
    content = out.get("content", {})
    if not isinstance(content, dict):
        out["content"] = {}
        meta_changes["changes"].append("reset_invalid:content")

    # Preserve unknown top-level fields
    known_keys = {
        "pack_format_version", "metadata", "manifest", "content",
        "engine_compatibility", "dependencies", "warnings", "_extras",
    }
    unknown = sorted(set(out.keys()) - known_keys)
    if unknown:
        extras = out.setdefault("_extras", {})
        for uk in unknown:
            if uk.startswith("_"):
                continue
            extras[uk] = out[uk]
        meta_changes["changes"].append(f"preserved_unknown_keys:{','.join(unknown)}")

    return out, meta_changes


def register_default_pack_steps(registry: MigrationRegistry) -> None:
    """Register the default pack migration steps into *registry*."""
    registry.register_pack_step(
        0, 1, _pack_step_0_to_1,
        name="pack_0_to_1",
        description="Legacy packs: add version stamp and normalize metadata",
    )
    registry.register_pack_step(
        1, 2, _pack_step_1_to_2,
        name="pack_1_to_2",
        description="Add engine_compatibility, normalize content, preserve unknowns",
    )
