"""Panel and adventure-pack delegates for GameLoop."""
from __future__ import annotations

from ..packs.models import AdventurePack


class GameLoopPanelsPacksMixin:
    # ------------------------------------------------------------------
    # Phase 7.6 — Social State Dashboard / Query
    # ------------------------------------------------------------------

    def get_social_dashboard(self) -> dict:
        """Return a presenter-shaped social state dashboard."""
        if self.social_state_core is None:
            return {"title": "Social State", "relationships": [], "rumors": [], "alliances": []}
        state = self.social_state_core.get_state()
        return {
            "title": "Social State",
            "relationships": [r.to_dict() for r in state.relationships.values()],
            "rumors": [r.to_dict() for r in state.rumors.values()],
            "alliances": [a.to_dict() for a in state.alliances.values()],
        }

    # ------------------------------------------------------------------
    # Phase 7.7 — Memory / Read-Model Panels
    # ------------------------------------------------------------------

    def get_journal_panel(self) -> dict:
        """Return a presenter-shaped journal panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Journal", "items": [], "count": 0}
        entries = [e.to_dict() for e in self.campaign_memory_core.journal_entries]
        return self.memory_presenter.present_journal_entries(entries)

    def get_recap_panel(self) -> dict:
        """Return a presenter-shaped recap panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
        recap = self.campaign_memory_core.last_recap
        if recap is None:
            return {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
        return self.memory_presenter.present_recap(recap.to_dict())

    def get_codex_panel(self) -> dict:
        """Return a presenter-shaped codex panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Codex", "items": [], "count": 0}
        entries = [e.to_dict() for e in self.campaign_memory_core.codex_entries.values()]
        return self.memory_presenter.present_codex(entries)

    def get_campaign_memory_panel(self) -> dict:
        """Return a presenter-shaped campaign memory panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
        snapshot = self.campaign_memory_core.last_campaign_snapshot
        if snapshot is None:
            return {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
        return self.memory_presenter.present_campaign_memory(snapshot.to_dict())

    # ------------------------------------------------------------------
    # Phase 7.8 — Arc Control Panels
    # ------------------------------------------------------------------

    def get_arc_panel(self) -> dict:
        """Return a presenter-shaped arc panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Arcs", "items": [], "count": 0}
        return self.arc_control_presenter.present_arc_panel(self.arc_control_controller)

    def get_reveal_panel(self) -> dict:
        """Return a presenter-shaped reveal panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Reveals", "items": [], "count": 0}
        return self.arc_control_presenter.present_reveal_panel(self.arc_control_controller)

    def get_scene_bias_panel(self) -> dict:
        """Return a presenter-shaped scene-bias panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Scene Bias", "items": [], "count": 0}
        return self.arc_control_presenter.present_scene_bias_panel(self.arc_control_controller)

    # ------------------------------------------------------------------
    # Phase 7.9 — Adventure Pack Operations
    # ------------------------------------------------------------------

    def register_pack(self, pack_data: dict) -> dict:
        """Deserialize, validate, and register an adventure pack.

        Returns a presenter-shaped result with validation and pack info.
        Phase 8.5: runs pack migration/normalization before registration.
        """
        # Phase 8.5 — migrate/normalize pack data before registration
        compat = self.pack_migrator.check_compatibility(pack_data)
        if not compat.compatible:
            return {
                "ok": False,
                "validation": {"issues": compat.errors, "is_blocking": True},
                "migration_report": compat.to_dict(),
            }

        migrated = self.pack_migrator.migrate(pack_data)
        if migrated.report.errors:
            return {
                "ok": False,
                "validation": {"issues": migrated.report.errors, "is_blocking": True},
                "migration_report": migrated.report.to_dict(),
            }

        pack = AdventurePack.from_dict(migrated.payload)
        validation = self.pack_validator.validate(pack)
        validation_dict = validation.to_dict()
        presented_validation = self.pack_presenter.present_validation_result(validation_dict)

        if validation.is_blocking():
            return {
                "ok": False,
                "validation": presented_validation,
                "migration_report": migrated.report.to_dict(),
            }

        self.pack_registry.register(pack)
        return {
            "ok": True,
            "validation": presented_validation,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
            "migration_report": migrated.report.to_dict(),
        }

    def list_registered_packs(self) -> dict:
        """Return a presenter-shaped list of all registered packs."""
        packs = self.pack_registry.list_packs()
        return self.pack_presenter.present_pack_list([p.to_dict() for p in packs])

    def load_registered_packs(self, pack_ids: list[str]) -> dict:
        """Load specified registered packs and return a structured seed payload.

        Does not mutate game state — returns a translation payload only.
        """
        packs: list[AdventurePack] = []
        missing: list[str] = []
        for pack_id in pack_ids:
            pack = self.pack_registry.get(pack_id)
            if pack is None:
                missing.append(pack_id)
            else:
                packs.append(pack)

        if missing:
            return {"ok": False, "reason": "missing_packs", "missing": missing}

        payload = self.pack_loader.load_many(packs)
        return {
            "ok": True,
            "payload": payload,
            "presented": self.pack_presenter.present_load_result(payload),
        }

    def merge_registered_packs(self, pack_ids: list[str]) -> dict:
        """Merge specified registered packs and return the merged pack.

        Does not register the merged result — callers can register it
        separately if desired.
        """
        packs: list[AdventurePack] = []
        missing: list[str] = []
        for pack_id in pack_ids:
            pack = self.pack_registry.get(pack_id)
            if pack is None:
                missing.append(pack_id)
            else:
                packs.append(pack)

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
        """Export current creator/GM state as an adventure pack."""
        creator_state = getattr(self, "creator_canon_state", None)
        pack = self.pack_exporter.export_from_creator_state(
            creator_canon_state=creator_state,
            title=title,
            version=version,
            pack_id=pack_id,
        )
        return {
            "ok": True,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
            "pack_data": pack.to_dict(),
        }

