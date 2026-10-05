"""Phase 7.7 — Memory Presenters.

UI-safe presentation layer for memory outputs.
Returns stable shapes suitable for frontend rendering.
"""

from __future__ import annotations


class MemoryPresenter:
    """UI-safe presenter for memory outputs."""

    def present_journal_entries(self, entries: list[dict]) -> dict:
        """Present a list of journal entries as a UI-safe panel."""
        items = [self.present_journal_entry(e) for e in entries]
        return {
            "title": "Journal",
            "items": items,
            "count": len(items),
        }

    def present_recap(self, recap: dict) -> dict:
        """Present a recap snapshot as a UI-safe panel."""
        return {
            "title": recap.get("title", "Recap"),
            "summary": recap.get("summary", ""),
            "scene_summary": recap.get("scene_summary", {}),
            "active_threads": recap.get("active_threads", []),
            "recent_consequences": recap.get("recent_consequences", []),
            "social_highlights": recap.get("social_highlights", []),
        }

    def present_codex(self, entries: list[dict]) -> dict:
        """Present codex entries as a UI-safe panel."""
        items = [self.present_codex_entry(e) for e in entries]
        return {
            "title": "Codex",
            "items": items,
            "count": len(items),
        }

    def present_campaign_memory(self, snapshot: dict) -> dict:
        """Present a campaign memory snapshot as a UI-safe panel."""
        return {
            "title": snapshot.get("title", "Campaign Memory"),
            "current_scene": snapshot.get("current_scene", {}),
            "active_threads": snapshot.get("active_threads", []),
            "resolved_threads": snapshot.get("resolved_threads", []),
            "major_consequences": snapshot.get("major_consequences", []),
            "social_summary": snapshot.get("social_summary", {}),
            "canon_summary": snapshot.get("canon_summary", {}),
        }

    def present_codex_entry(self, entry: dict) -> dict:
        """Present a single codex entry as a UI-safe dict."""
        return {
            "entry_id": entry.get("entry_id", ""),
            "entry_type": entry.get("entry_type", ""),
            "title": entry.get("title", ""),
            "summary": entry.get("summary", ""),
            "canonical": entry.get("canonical", True),
            "tags": entry.get("tags", []),
        }

    def present_journal_entry(self, entry: dict) -> dict:
        """Present a single journal entry as a UI-safe dict.

        Fix 7: whitelist fields only — no raw metadata passed through.
        """
        return {
            "id": entry.get("entry_id"),
            "title": entry.get("title"),
            "summary": entry.get("summary"),
            "type": entry.get("entry_type"),
            "entities": entry.get("entity_ids", []),
            "threads": entry.get("thread_ids", []),
            "location": entry.get("location"),
        }
