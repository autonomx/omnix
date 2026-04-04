"""Phase 7.9 — Pack Merger.

Deterministic merge rules for multiple adventure packs.
Default: error on duplicate IDs across packs unless namespaced distinctly.
"""

from __future__ import annotations

from .models import (
    AdventurePack,
    PackContent,
    PackManifest,
    PackMetadata,
)


class PackMergeConflictError(Exception):
    """Raised when packs have conflicting IDs or declared conflicts."""


class PackMerger:
    """Merge multiple adventure packs deterministically."""

    def merge(self, packs: list[AdventurePack]) -> AdventurePack:
        """Merge a list of packs into a single combined pack.

        Merge order is deterministic (list order).  First-wins for metadata.
        Content lists are concatenated. Duplicate IDs across packs cause an
        error unless they resolve to distinct namespaced values.
        """
        if not packs:
            from .schema import build_empty_pack
            return build_empty_pack("merged", "Merged Pack", "0.0.0")
        if len(packs) == 1:
            return AdventurePack.from_dict(packs[0].to_dict())

        self._check_conflicts(packs)

        return AdventurePack(
            metadata=self._merge_metadata(packs),
            manifest=self._merge_manifest(packs),
            content=self._merge_content(packs),
        )

    def _merge_metadata(self, packs: list[AdventurePack]) -> PackMetadata:
        """First pack wins for identity; tags are unioned."""
        first = packs[0].metadata
        all_tags: list[str] = []
        seen_tags: set[str] = set()
        for pack in packs:
            for tag in pack.metadata.tags:
                if tag not in seen_tags:
                    all_tags.append(tag)
                    seen_tags.add(tag)

        return PackMetadata(
            pack_id=f"merged_{'_'.join(p.metadata.pack_id for p in packs)}",
            title=f"Merged: {first.title}",
            version=first.version,
            author=first.author,
            description=f"Merged from {len(packs)} packs",
            tags=all_tags,
            requires_engine_version=first.requires_engine_version,
            metadata={"source_packs": [p.metadata.pack_id for p in packs]},
        )

    def _merge_manifest(self, packs: list[AdventurePack]) -> PackManifest:
        """Merge manifests: union dependencies, union conflicts, union namespaces."""
        deps: list[str] = []
        deps_seen: set[str] = set()
        conflicts: list[str] = []
        conflicts_seen: set[str] = set()
        namespaces: list[str] = []
        ns_seen: set[str] = set()

        for pack in packs:
            for dep in pack.manifest.dependencies:
                if dep not in deps_seen:
                    deps.append(dep)
                    deps_seen.add(dep)
            for conflict in pack.manifest.conflicts:
                if conflict not in conflicts_seen:
                    conflicts.append(conflict)
                    conflicts_seen.add(conflict)
            for ns in pack.manifest.namespaces:
                if ns not in ns_seen:
                    namespaces.append(ns)
                    ns_seen.add(ns)

        merged_id = f"merged_{'_'.join(p.metadata.pack_id for p in packs)}"
        return PackManifest(
            manifest_id=f"{merged_id}_manifest",
            pack_id=merged_id,
            content_version=packs[0].manifest.content_version,
            dependencies=deps,
            conflicts=conflicts,
            namespaces=namespaces,
            metadata={"source_packs": [p.metadata.pack_id for p in packs]},
        )

    def _merge_content(self, packs: list[AdventurePack]) -> PackContent:
        """Merge content lists with duplicate-ID detection."""
        all_creator_facts: list[dict] = []
        all_setup_templates: list[dict] = []
        all_social_seeds: list[dict] = []
        all_reveal_seeds: list[dict] = []
        all_pacing_presets: list[dict] = []
        all_gm_presets: list[dict] = []

        for pack in packs:
            c = pack.content
            all_creator_facts.extend(c.creator_facts)
            all_setup_templates.extend(c.setup_templates)
            all_social_seeds.extend(c.social_seeds)
            all_reveal_seeds.extend(c.reveal_seeds)
            all_pacing_presets.extend(c.pacing_presets)
            all_gm_presets.extend(c.gm_presets)

        # ID-keyed lists — detect duplicates
        factions = self._merge_list_by_id(
            [item for p in packs for item in p.content.factions], "faction_id"
        )
        locations = self._merge_list_by_id(
            [item for p in packs for item in p.content.locations], "location_id"
        )
        npcs = self._merge_list_by_id(
            [item for p in packs for item in p.content.npcs], "npc_id"
        )
        threads = self._merge_list_by_id(
            [item for p in packs for item in p.content.threads], "thread_id"
        )
        arcs = self._merge_list_by_id(
            [item for p in packs for item in p.content.arcs], "arc_id"
        )

        return PackContent(
            creator_facts=all_creator_facts,
            setup_templates=all_setup_templates,
            factions=factions,
            locations=locations,
            npcs=npcs,
            threads=threads,
            arcs=arcs,
            social_seeds=all_social_seeds,
            reveal_seeds=all_reveal_seeds,
            pacing_presets=all_pacing_presets,
            gm_presets=all_gm_presets,
        )

    def _merge_list_by_id(self, items: list[dict], id_key: str) -> list[dict]:
        """Merge a list of dict items, erroring on duplicate IDs."""
        seen: dict[str, dict] = {}
        result: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                result.append(item)
                continue
            item_id = item.get(id_key)
            if isinstance(item_id, str) and item_id:
                if item_id in seen:
                    raise PackMergeConflictError(
                        f"Duplicate {id_key} '{item_id}' across packs"
                    )
                seen[item_id] = item
            result.append(item)
        return result

    def _check_conflicts(self, packs: list[AdventurePack]) -> None:
        """Check for declared conflicts between packs."""
        pack_ids = {p.metadata.pack_id for p in packs}
        for pack in packs:
            for conflict_id in pack.manifest.conflicts:
                if conflict_id in pack_ids:
                    raise PackMergeConflictError(
                        f"Pack '{pack.metadata.pack_id}' declares conflict "
                        f"with '{conflict_id}', which is also being merged"
                    )
