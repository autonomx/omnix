"""Phase 7.7 — Campaign Memory Core.

Central owner for derived memory state. This is a read-model / memory layer,
not a simulation layer. It derives from coherence, social state, creator canon,
and GM directives. It must never mutate those authoritative systems.

Snapshot memory state is preserved only for UX continuity, not because it is
authoritative.
"""

from __future__ import annotations

from typing import Any

from .campaign_memory_builder import CampaignMemoryBuilder
from .codex_builder import CodexBuilder
from .journal_builder import JournalBuilder
from .models import (
    CampaignMemorySnapshot,
    CodexEntry,
    JournalEntry,
    RecapSnapshot,
)
from .presenters import MemoryPresenter
from .recap_builder import RecapBuilder


class CampaignMemoryCore:
    """Central owner for derived memory state.

    This is derived state, but it is still useful to snapshot for UX continuity.
    """

    def __init__(self) -> None:
        self.journal_entries: list[JournalEntry] = []
        self.last_recap: RecapSnapshot | None = None
        self.last_campaign_snapshot: CampaignMemorySnapshot | None = None
        self.codex_entries: dict[str, CodexEntry] = {}
        self._mode: str = "live"
        # Fix 1: bounded journal with deterministic trimming
        self._max_entries: int = 500
        # Fix 5: bounded snapshot history
        self._snapshot_history: list[CampaignMemorySnapshot] = []
        self._max_snapshots: int = 50

        self._journal_builder = JournalBuilder()
        self._recap_builder = RecapBuilder()
        self._codex_builder = CodexBuilder()
        self._campaign_memory_builder = CampaignMemoryBuilder()
        self._presenter = MemoryPresenter()

    def set_mode(self, mode: str) -> None:
        """Set replay/live mode."""
        self._mode = mode

    def record_action_resolution(
        self,
        resolution: dict,
        coherence_core: Any,
        social_state_core: Any | None = None,
        tick: int | None = None,
    ) -> None:
        """Record journal entries from an action resolution."""
        new_entries = self._journal_builder.build_from_action_resolution(
            resolution=resolution,
            coherence_core=coherence_core,
            social_state_core=social_state_core,
            tick=tick,
        )
        self.journal_entries.extend(new_entries)

        thread_entries = self._journal_builder.build_from_thread_changes(
            coherence_core=coherence_core,
            tick=tick,
        )
        self.journal_entries.extend(thread_entries)

        # Fix 1: deterministic trimming after entries are added
        self._trim_journal_if_needed()

    def _trim_journal_if_needed(self) -> None:
        """Fix 1: deterministic bounded journal trimming."""
        if len(self.journal_entries) > self._max_entries:
            overflow = len(self.journal_entries) - self._max_entries
            self.journal_entries = self.journal_entries[overflow:]

    def refresh_recap(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
        creator_canon_state: Any | None = None,
        tick: int | None = None,
    ) -> dict:
        """Refresh the recap snapshot and return a presenter-shaped payload."""
        self.last_recap = self._recap_builder.build(
            coherence_core=coherence_core,
            social_state_core=social_state_core,
            creator_canon_state=creator_canon_state,
            tick=tick,
        )
        return self._presenter.present_recap(self.last_recap.to_dict())

    def refresh_codex(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
        creator_canon_state: Any | None = None,
    ) -> dict:
        """Refresh codex entries and return a presenter-shaped payload."""
        all_entries: list[CodexEntry] = []
        all_entries.extend(self._codex_builder.build_npc_entries(coherence_core, social_state_core))
        all_entries.extend(self._codex_builder.build_faction_entries(coherence_core, social_state_core))
        all_entries.extend(self._codex_builder.build_location_entries(coherence_core))
        all_entries.extend(self._codex_builder.build_lore_entries(creator_canon_state))
        all_entries.extend(self._codex_builder.build_rumor_entries(social_state_core))
        all_entries.extend(self._codex_builder.build_thread_entries(coherence_core))

        self.codex_entries = {e.entry_id: e for e in all_entries}
        return self._presenter.present_codex([e.to_dict() for e in all_entries])

    def refresh_campaign_snapshot(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
        creator_canon_state: Any | None = None,
        tick: int | None = None,
    ) -> dict:
        """Refresh the campaign memory snapshot and return a presenter-shaped payload."""
        snapshot = self._campaign_memory_builder.build(
            coherence_core=coherence_core,
            social_state_core=social_state_core,
            creator_canon_state=creator_canon_state,
            tick=tick,
        )
        self.last_campaign_snapshot = snapshot

        # Fix 5: keep bounded snapshot history
        self._snapshot_history.append(snapshot)
        if len(self._snapshot_history) > self._max_snapshots:
            self._snapshot_history = self._snapshot_history[-self._max_snapshots:]

        return self._presenter.present_campaign_memory(snapshot.to_dict())

    def serialize_state(self) -> dict:
        """Serialize derived memory state for snapshot persistence.

        Fix 8: defensive copy — return fresh dicts so callers cannot
        mutate internal state.
        """
        return {
            "journal_entries": [dict(e.to_dict()) for e in self.journal_entries],
            "last_recap": dict(self.last_recap.to_dict()) if self.last_recap else None,
            "last_campaign_snapshot": (
                dict(self.last_campaign_snapshot.to_dict()) if self.last_campaign_snapshot else None
            ),
            "codex_entries": {k: dict(v.to_dict()) for k, v in self.codex_entries.items()},
            "mode": self._mode,
        }

    def deserialize_state(self, data: dict) -> None:
        """Restore derived memory state from a serialized snapshot."""
        self.journal_entries = [
            JournalEntry.from_dict(e) for e in data.get("journal_entries", [])
        ]
        recap_data = data.get("last_recap")
        self.last_recap = RecapSnapshot.from_dict(recap_data) if recap_data else None
        snapshot_data = data.get("last_campaign_snapshot")
        self.last_campaign_snapshot = (
            CampaignMemorySnapshot.from_dict(snapshot_data) if snapshot_data else None
        )
        self.codex_entries = {
            k: CodexEntry.from_dict(v) for k, v in data.get("codex_entries", {}).items()
        }
        self._mode = data.get("mode", "live")
