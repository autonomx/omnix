"""Phase 7.8 — Arc Registry.

Central manager for active/dormant/resolved narrative arcs.
Derives initial arcs from unresolved coherence threads and allows
explicit creator/GM steering to override status/priority.
"""

from __future__ import annotations

from typing import Any

from .models import NarrativeArc


class ArcRegistry:
    """Central manager for narrative arcs."""

    # ------------------------------------------------------------------
    # Query / mutation helpers
    # ------------------------------------------------------------------

    def list_arcs(self, state: dict[str, NarrativeArc]) -> list[NarrativeArc]:
        """Return all arcs currently registered."""
        return list(state.values())

    def get_arc(
        self, state: dict[str, NarrativeArc], arc_id: str
    ) -> NarrativeArc | None:
        """Return a single arc by ID, or ``None``."""
        return state.get(arc_id)

    def upsert_arc(
        self, state: dict[str, NarrativeArc], arc: NarrativeArc
    ) -> None:
        """Insert or replace an arc in the registry."""
        state[arc.arc_id] = arc

    def set_status(
        self,
        state: dict[str, NarrativeArc],
        arc_id: str,
        status: str,
    ) -> None:
        """Update the status of an existing arc (no-op if missing)."""
        arc = state.get(arc_id)
        if arc is not None:
            arc.status = status

    # ------------------------------------------------------------------
    # Coherence → arc derivation
    # ------------------------------------------------------------------

    def build_from_threads(
        self, coherence_core: Any
    ) -> list[NarrativeArc]:
        """Derive arcs from unresolved coherence threads.

        Each unresolved thread becomes a candidate ``NarrativeArc`` with
        ``status="active"`` and ``arc_type="general"``.  The caller
        decides whether to merge these into the canonical arc state.
        """
        threads = (
            coherence_core.get_unresolved_threads()
            if coherence_core is not None
            else []
        )
        arcs: list[NarrativeArc] = []
        for thread in threads:
            thread_id = (
                thread.get("thread_id", "")
                if isinstance(thread, dict)
                else getattr(thread, "thread_id", "")
            )
            title = (
                thread.get("title", thread_id)
                if isinstance(thread, dict)
                else getattr(thread, "title", thread_id)
            )
            arcs.append(
                NarrativeArc(
                    arc_id=f"arc:{thread_id}",
                    title=title,
                    status="active",
                    priority="normal",
                    arc_type="general",
                    related_thread_ids=[thread_id] if thread_id else [],
                )
            )
        return arcs

    def refresh_from_coherence(
        self,
        state: dict[str, NarrativeArc],
        coherence_core: Any,
    ) -> None:
        """Refresh the arc registry by reconciling against coherence.

        New arcs are inserted; existing arcs have structural fields
        refreshed while preserving steering fields (priority/status).
        Arcs that no longer exist in coherence are removed.
        """
        new_arcs = self.build_from_threads(coherence_core)
        new_ids = {a.arc_id for a in new_arcs}

        # Upsert current arcs
        for arc in new_arcs:
            if arc.arc_id in state:
                # preserve steering fields (priority/status) but refresh structural fields
                existing = state[arc.arc_id]
                existing.title = arc.title
                existing.related_thread_ids = arc.related_thread_ids
                existing.focus_entity_ids = arc.focus_entity_ids
            else:
                state[arc.arc_id] = arc

        # Remove arcs that no longer exist in coherence
        to_remove = [arc_id for arc_id in state if arc_id not in new_ids]
        for arc_id in to_remove:
            del state[arc_id]
