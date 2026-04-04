"""Phase 7.7 — Journal Builder.

Build chronological journal entries from current state and recent outcomes.
This is a read-model builder — it derives entries from authoritative state
and must never mutate coherence or social state.
"""

from __future__ import annotations

from typing import Any

from .models import JournalEntry


class JournalBuilder:
    """Build journal entries from action resolutions and state changes."""

    def build_from_action_resolution(
        self,
        resolution: dict,
        coherence_core: Any,
        social_state_core: Any | None = None,
        tick: int | None = None,
    ) -> list[JournalEntry]:
        """Build journal entries from a resolved action result dict."""
        entries: list[JournalEntry] = []

        resolved = resolution.get("resolved_action", {})
        action_title = resolved.get("title") or resolved.get("action_name", "Action")
        action_summary = resolved.get("summary") or resolved.get("description", "An action was resolved.")
        entity_ids = list(resolved.get("entity_ids", []))

        entries.append(
            JournalEntry(
                entry_id=self._entry_id("action", tick, resolved.get("action_id", "unknown")),
                tick=tick,
                entry_type="action",
                title=action_title,
                summary=action_summary,
                entity_ids=entity_ids,
                location=resolved.get("location"),
                metadata={"source": "action_resolution"},
            )
        )

        # Extract consequence entries
        for consequence in resolution.get("consequences", []):
            c_summary = consequence.get("summary", "")
            c_entity_ids = list(consequence.get("entity_ids", []))
            if c_summary:
                entries.append(
                    JournalEntry(
                        entry_id=self._entry_id("consequence", tick, consequence.get("consequence_id", "c")),
                        tick=tick,
                        entry_type="action",
                        title="Consequence",
                        summary=c_summary,
                        entity_ids=c_entity_ids,
                        location=resolved.get("location"),
                        metadata={"source": "consequence"},
                    )
                )

        return entries

    def build_from_scene_transition(
        self,
        transition: dict,
        tick: int | None = None,
    ) -> JournalEntry | None:
        """Build a journal entry from a scene transition."""
        destination = transition.get("destination", "")
        reason = transition.get("reason", "")
        if not destination and not reason:
            return None

        summary = f"Scene transition to {destination}." if destination else "Scene transition."
        if reason:
            summary += f" Reason: {reason}"

        return JournalEntry(
            entry_id=self._entry_id("transition", tick, destination or "unknown"),
            tick=tick,
            entry_type="transition",
            title=f"Transition: {destination}" if destination else "Scene Transition",
            summary=summary,
            location=destination or None,
            metadata={"source": "scene_transition"},
        )

    def build_from_thread_changes(
        self,
        coherence_core: Any,
        tick: int | None = None,
    ) -> list[JournalEntry]:
        """Build journal entries from thread state changes."""
        entries: list[JournalEntry] = []
        state = coherence_core.get_state()

        for thread_id, thread in state.unresolved_threads.items():
            if thread.status == "resolved" and thread.resolved_tick == tick:
                entries.append(
                    JournalEntry(
                        entry_id=self._entry_id("thread_resolution", tick, thread_id),
                        tick=tick,
                        entry_type="thread_resolution",
                        title=f"Thread Resolved: {thread.title}",
                        summary=f"The thread '{thread.title}' has been resolved.",
                        entity_ids=list(thread.anchor_entity_ids),
                        thread_ids=[thread_id],
                        metadata={"source": "thread_change"},
                    )
                )
            elif thread.updated_tick == tick and thread.status != "resolved":
                entries.append(
                    JournalEntry(
                        entry_id=self._entry_id("thread_progress", tick, thread_id),
                        tick=tick,
                        entry_type="thread_progress",
                        title=f"Thread Updated: {thread.title}",
                        summary=f"The thread '{thread.title}' has progressed.",
                        entity_ids=list(thread.anchor_entity_ids),
                        thread_ids=[thread_id],
                        metadata={"source": "thread_change"},
                    )
                )

        return entries

    def build_from_social_changes(
        self,
        social_state_core: Any,
        tick: int | None = None,
    ) -> list[JournalEntry]:
        """Build journal entries from social state changes (rumors, relationships)."""
        entries: list[JournalEntry] = []
        if social_state_core is None:
            return entries

        state = social_state_core.get_state()

        # Rumor entries
        for rumor_id, rumor in state.rumors.items():
            if rumor.active:
                entries.append(
                    JournalEntry(
                        entry_id=self._entry_id("rumor", tick, rumor_id),
                        tick=tick,
                        entry_type="rumor",
                        title=f"Rumor: {rumor.summary[:50]}",
                        summary=rumor.summary,
                        entity_ids=[eid for eid in [rumor.source_npc_id, rumor.subject_id] if eid],
                        location=rumor.location,
                        metadata={"source": "social_state", "rumor_id": rumor_id},
                    )
                )

        return entries

    def _entry_id(self, prefix: str, tick: int | None, key: str) -> str:
        """Generate a deterministic entry ID."""
        tick_part = str(tick) if tick is not None else "none"
        return f"journal:{prefix}:{tick_part}:{key}"
