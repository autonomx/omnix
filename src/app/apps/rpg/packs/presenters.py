"""Phase 7.9 — Pack Presenters.

UI-safe pack panels with stable output shapes.
"""

from __future__ import annotations


class PackPresenter:
    """Present pack data in UI-safe formats."""

    def present_pack_list(self, packs: list[dict]) -> dict:
        """Present a list of packs for the UI."""
        packs = sorted(packs, key=lambda p: p.get("metadata", {}).get("pack_id", ""))
        items = []
        for pack in packs:
            meta = pack.get("metadata", {})
            items.append({
                "pack_id": meta.get("pack_id", ""),
                "title": meta.get("title", ""),
                "version": meta.get("version", ""),
                "author": meta.get("author", ""),
                "description": meta.get("description", ""),
                "tags": list(meta.get("tags", [])),
            })
        return {
            "title": "Adventure Packs",
            "items": items,
            "count": len(items),
        }

    def present_pack(self, pack: dict) -> dict:
        """Present a single pack for the UI."""
        meta = pack.get("metadata", {})
        manifest = pack.get("manifest", {})
        content = pack.get("content", {})

        content_summary: dict[str, int] = {}
        for field_name in (
            "creator_facts",
            "setup_templates",
            "factions",
            "locations",
            "npcs",
            "threads",
            "arcs",
            "social_seeds",
            "reveal_seeds",
            "pacing_presets",
            "gm_presets",
        ):
            items = content.get(field_name, [])
            if items:
                content_summary[field_name] = len(items)

        return {
            "pack_id": meta.get("pack_id", ""),
            "title": meta.get("title", ""),
            "version": meta.get("version", ""),
            "author": meta.get("author", ""),
            "description": meta.get("description", ""),
            "tags": list(meta.get("tags", [])),
            "dependencies": list(manifest.get("dependencies", [])),
            "conflicts": list(manifest.get("conflicts", [])),
            "namespaces": list(manifest.get("namespaces", [])),
            "content_summary": content_summary,
        }

    def present_validation_result(self, result: dict) -> dict:
        """Present a validation result for the UI."""
        issues = result.get("issues", [])
        return {
            "title": "Pack Validation",
            "is_blocking": result.get("is_blocking", False),
            "issue_count": len(issues),
            "issues": [
                {
                    "path": issue.get("path", ""),
                    "code": issue.get("code", ""),
                    "message": issue.get("message", ""),
                    "severity": issue.get("severity", "error"),
                }
                for issue in issues
            ],
        }

    def present_load_result(self, payload: dict) -> dict:
        """Present a load result for the UI."""
        sections: list[dict] = []
        for key in ("creator_seed", "arc_seed", "social_seed", "memory_seed"):
            seed = payload.get(key, {})
            if seed:
                sections.append({
                    "section": key,
                    "keys": list(seed.keys()),
                    "item_count": sum(
                        len(v) for v in seed.values()
                        if isinstance(v, list)
                    ),
                })
        return {
            "title": "Pack Load Result",
            "sections": sections,
            "section_count": len(sections),
        }
