"""Phase 7.9 — Pack Exporter.

Export current configuration/state-derived content into pack format.
Conservative export: creator canon, templates, selected seeds only.
"""

from __future__ import annotations

from typing import Any

from .models import (
    AdventurePack,
    PackContent,
    PackManifest,
    PackMetadata,
)


class PackExporter:
    """Export current state into adventure pack format."""

    def export_from_creator_state(
        self,
        creator_canon_state: Any,
        title: str,
        version: str,
        pack_id: str,
    ) -> AdventurePack:
        """Export an adventure pack from creator canon state.

        Extracts canon facts, templates, factions, locations, NPCs, and
        threads from the creator canon state.
        """
        metadata = PackMetadata(
            pack_id=pack_id,
            title=title,
            version=version,
            description="Exported from creator canon state",
        )
        manifest = PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        )

        # Extract content from creator canon state
        creator_facts: list[dict] = []
        factions: list[dict] = []
        locations: list[dict] = []
        npcs: list[dict] = []
        threads: list[dict] = []

        if creator_canon_state is not None:
            state_data = {}
            if hasattr(creator_canon_state, "serialize_state"):
                state_data = creator_canon_state.serialize_state()
            elif isinstance(creator_canon_state, dict):
                state_data = creator_canon_state

            # Extract facts as creator_facts
            facts = state_data.get("facts", {})
            if isinstance(facts, dict):
                for key, val in facts.items():
                    if isinstance(val, dict):
                        creator_facts.append(dict(val))
                    else:
                        creator_facts.append({"key": key, "value": val})

            # Extract setup data if available
            setup = state_data.get("setup", {})
            if isinstance(setup, dict):
                factions = list(setup.get("factions", []))
                locations = list(setup.get("locations", []))
                npcs = list(setup.get("npc_seeds", []))

        content = PackContent(
            creator_facts=creator_facts,
            factions=factions,
            locations=locations,
            npcs=npcs,
            threads=threads,
        )

        return AdventurePack(
            metadata=metadata,
            manifest=manifest,
            content=content,
        )

    def export_from_current_setup(
        self,
        setup: Any,
        title: str,
        version: str,
        pack_id: str,
    ) -> AdventurePack:
        """Export an adventure pack from the current adventure setup.

        Extracts factions, locations, NPCs, themes, pacing, and setup
        templates from the AdventureSetup.
        """
        metadata = PackMetadata(
            pack_id=pack_id,
            title=title,
            version=version,
            description="Exported from current adventure setup",
        )
        manifest = PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        )

        setup_data: dict = {}
        if hasattr(setup, "to_dict"):
            setup_data = setup.to_dict()
        elif isinstance(setup, dict):
            setup_data = setup

        factions = list(setup_data.get("factions", []))
        locations = list(setup_data.get("locations", []))
        npcs = list(setup_data.get("npc_seeds", []))
        threads: list[dict] = []

        # Extract pacing as a preset if available
        pacing_presets: list[dict] = []
        pacing = setup_data.get("pacing")
        if isinstance(pacing, dict):
            pacing_presets.append(pacing)

        # Create a setup template from the full setup
        setup_templates: list[dict] = []
        if setup_data:
            template = {
                "template_id": f"{pack_id}_template",
                "title": setup_data.get("title", title),
                "genre": setup_data.get("genre", ""),
                "setting": setup_data.get("setting", ""),
                "premise": setup_data.get("premise", ""),
            }
            setup_templates.append(template)

        content = PackContent(
            factions=factions,
            locations=locations,
            npcs=npcs,
            threads=threads,
            setup_templates=setup_templates,
            pacing_presets=pacing_presets,
        )

        return AdventurePack(
            metadata=metadata,
            manifest=manifest,
            content=content,
        )

    def export_minimal(
        self,
        title: str,
        version: str,
        pack_id: str,
    ) -> AdventurePack:
        """Export a minimal empty adventure pack.

        Phase 7.9 tightening — normalize through serialization for
        deterministic field ordering.
        """
        from .schema import build_empty_pack
        pack = build_empty_pack(pack_id, title, version)
        data = pack.to_dict()
        return AdventurePack.from_dict(data)
