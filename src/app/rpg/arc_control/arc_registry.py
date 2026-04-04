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
        """Refresh the arc registry by merging thread-derived arcs.

        New arcs are inserted; existing arcs are *not* overwritten so
        that explicit GM/creator steering is preserved.
        """
        derived = self.build_from_threads(coherence_core)
        for arc in derived:
            if arc.arc_id not in state:
                state[arc.arc_id] = arc
