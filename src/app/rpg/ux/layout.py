"""Phase 8.0 — Deterministic Panel Layout Planning.

Builds ordered lists of PanelDescriptor objects describing the panels
available to the player.  Layout order is deterministic.
"""

from __future__ import annotations

from .models import PanelDescriptor


# Deterministic default panel order
_DEFAULT_PANEL_ORDER: list[tuple[str, str, str]] = [
    ("recap", "Recap", "recap"),
    ("journal", "Journal", "journal"),
    ("codex", "Codex", "codex"),
    ("campaign_memory", "Campaign Memory", "campaign_memory"),
    ("social", "Social State", "social"),
    ("arc", "Arcs", "arc"),
    ("reveals", "Reveals", "reveals"),
    ("packs", "Adventure Packs", "packs"),
    ("scene_bias", "Scene Bias", "scene_bias"),
]


class PanelLayout:
    """Deterministic panel layout builder."""

    def build_default_layout(self) -> list[PanelDescriptor]:
        """Return the full default panel layout in deterministic order."""
        return [
            self._descriptor(pid, title, ptype)
            for pid, title, ptype in _DEFAULT_PANEL_ORDER
        ]

    def build_player_layout(
        self, available_panels: dict[str, dict]
    ) -> list[PanelDescriptor]:
        """Return panel descriptors for only the panels present in
        *available_panels*, preserving deterministic order.

        Args:
            available_panels: Mapping of panel_id → metadata dict.
                Each value may contain ``count`` and extra metadata keys.
        """
        result: list[PanelDescriptor] = []
        for pid, title, ptype in _DEFAULT_PANEL_ORDER:
            if pid in available_panels:
                meta = available_panels[pid]
                result.append(
                    self._descriptor(
                        pid,
                        title,
                        ptype,
                        count=meta.get("count"),
                    )
                )
        return result

    @staticmethod
    def _descriptor(
        panel_id: str,
        title: str,
        panel_type: str,
        count: int | None = None,
    ) -> PanelDescriptor:
        return PanelDescriptor(
            panel_id=panel_id,
            title=title,
            panel_type=panel_type,
            count=count,
        )
