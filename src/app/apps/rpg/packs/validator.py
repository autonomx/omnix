"""Phase 7.9 — Pack Validator.

Validate pack shape, compatibility, and content integrity.
Does not require internet or external version checks.
"""

from __future__ import annotations

from .models import AdventurePack, PackValidationIssue, PackValidationResult


class PackValidator:
    """Validate adventure packs for structural and content integrity."""

    def validate(self, pack: AdventurePack) -> PackValidationResult:
        """Run all validation checks and return aggregated result."""
        issues: list[PackValidationIssue] = []
        issues.extend(self._validate_metadata(pack))
        issues.extend(self._validate_manifest(pack))
        issues.extend(self._validate_content(pack))
        issues.extend(self._validate_ids_unique(pack))
        issues.extend(self._validate_dependencies(pack))
        issues.extend(self._validate_namespaces(pack))
        return PackValidationResult(issues=issues)

    def _validate_metadata(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check required metadata fields."""
        issues: list[PackValidationIssue] = []
        meta = pack.metadata
        if not meta.pack_id:
            issues.append(PackValidationIssue(
                path="metadata.pack_id",
                code="missing_pack_id",
                message="Pack ID is required",
            ))
        if not meta.title:
            issues.append(PackValidationIssue(
                path="metadata.title",
                code="missing_title",
                message="Pack title is required",
            ))
        if not meta.version:
            issues.append(PackValidationIssue(
                path="metadata.version",
                code="missing_version",
                message="Pack version is required",
            ))
        return issues

    def _validate_manifest(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check manifest consistency."""
        issues: list[PackValidationIssue] = []
        manifest = pack.manifest
        if not manifest.manifest_id:
            issues.append(PackValidationIssue(
                path="manifest.manifest_id",
                code="missing_manifest_id",
                message="Manifest ID is required",
            ))
        if manifest.pack_id and pack.metadata.pack_id and manifest.pack_id != pack.metadata.pack_id:
            issues.append(PackValidationIssue(
                path="manifest.pack_id",
                code="pack_id_mismatch",
                message="Manifest pack_id does not match metadata pack_id",
            ))
        # Check conflicts list sanity — a pack should not conflict with itself
        if pack.metadata.pack_id and pack.metadata.pack_id in manifest.conflicts:
            issues.append(PackValidationIssue(
                path="manifest.conflicts",
                code="self_conflict",
                message="Pack cannot conflict with itself",
            ))
        return issues

    def _validate_content(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check for malformed content objects."""
        issues: list[PackValidationIssue] = []
        content = pack.content

        # Validate content items are dicts
        content_fields = [
            ("creator_facts", content.creator_facts),
            ("setup_templates", content.setup_templates),
            ("factions", content.factions),
            ("locations", content.locations),
            ("npcs", content.npcs),
            ("threads", content.threads),
            ("arcs", content.arcs),
            ("social_seeds", content.social_seeds),
            ("reveal_seeds", content.reveal_seeds),
            ("pacing_presets", content.pacing_presets),
            ("gm_presets", content.gm_presets),
        ]

        for field_name, items in content_fields:
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    issues.append(PackValidationIssue(
                        path=f"content.{field_name}[{idx}]",
                        code="malformed_content_item",
                        message=f"Content item at {field_name}[{idx}] must be a dict",
                    ))
        return issues

    def _validate_ids_unique(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check for duplicate IDs within a single pack."""
        issues: list[PackValidationIssue] = []
        content = pack.content

        id_fields = [
            ("factions", content.factions, "faction_id"),
            ("locations", content.locations, "location_id"),
            ("npcs", content.npcs, "npc_id"),
            ("threads", content.threads, "thread_id"),
            ("arcs", content.arcs, "arc_id"),
        ]

        for field_name, items, id_key in id_fields:
            seen: set[str] = set()
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                item_id = item.get(id_key)
                if isinstance(item_id, str) and item_id:
                    if item_id in seen:
                        issues.append(PackValidationIssue(
                            path=f"content.{field_name}[{idx}].{id_key}",
                            code="duplicate_id",
                            message=f"Duplicate {id_key}: {item_id}",
                        ))
                    seen.add(item_id)
        return issues

    def _validate_dependencies(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check dependency references for basic sanity."""
        issues: list[PackValidationIssue] = []
        manifest = pack.manifest

        # A pack should not depend on itself
        if pack.metadata.pack_id and pack.metadata.pack_id in manifest.dependencies:
            issues.append(PackValidationIssue(
                path="manifest.dependencies",
                code="self_dependency",
                message="Pack cannot depend on itself",
                severity="warning",
            ))

        # Dependencies and conflicts should not overlap
        overlap = set(manifest.dependencies) & set(manifest.conflicts)
        if overlap:
            for dep in sorted(overlap):
                issues.append(PackValidationIssue(
                    path="manifest",
                    code="dependency_conflict_overlap",
                    message=f"Pack '{dep}' is both a dependency and a conflict",
                ))
        return issues

    def _validate_namespaces(self, pack: AdventurePack) -> list[PackValidationIssue]:
        """Check namespace consistency."""
        issues: list[PackValidationIssue] = []
        manifest = pack.manifest

        # Namespaces should not be empty strings
        for idx, ns in enumerate(manifest.namespaces):
            if not isinstance(ns, str) or not ns.strip():
                issues.append(PackValidationIssue(
                    path=f"manifest.namespaces[{idx}]",
                    code="empty_namespace",
                    message=f"Namespace at index {idx} is empty",
                    severity="warning",
                ))

        # Namespace should not contain colons (used as separator)
        for idx, ns in enumerate(manifest.namespaces):
            if isinstance(ns, str) and ":" in ns:
                issues.append(PackValidationIssue(
                    path=f"manifest.namespaces[{idx}]",
                    code="invalid_namespace_char",
                    message=f"Namespace '{ns}' contains reserved character ':'",
                    severity="warning",
                ))
        return issues
