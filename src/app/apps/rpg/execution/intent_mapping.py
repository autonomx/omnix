"""Phase 7.3 — Intent Mapping.

Maps ChoiceOption intent_type into resolution categories and defaults.
This keeps resolution logic cleaner and makes it easy to extend new
option types later.
"""

from __future__ import annotations

from typing import Any


class ActionIntentMapper:
    """Map a ChoiceOption into a resolution descriptor dict."""

    def map_option(self, option: Any) -> dict:
        """Return a resolution descriptor for the given option.

        The option can be a ChoiceOption instance or a plain dict.
        """
        intent_type = self._get_field(option, "intent_type", "unknown")
        mapper = {
            "investigate_thread": self._map_investigate_thread,
            "talk_to_npc": self._map_talk_to_npc,
            "travel_to_location": self._map_travel_to_location,
            "request_recap": self._map_request_recap,
        }.get(intent_type, self._map_default)
        return mapper(option)

    # ------------------------------------------------------------------
    # Private mappers
    # ------------------------------------------------------------------

    def _map_investigate_thread(self, option: Any) -> dict:
        target_id = self._get_field(option, "target_id")
        return {
            "intent_type": "investigate_thread",
            "resolution_type": "thread_progress",
            "target_id": target_id,
            "summary": f"Investigate unresolved thread {target_id}",
        }

    def _map_talk_to_npc(self, option: Any) -> dict:
        target_id = self._get_field(option, "target_id")
        return {
            "intent_type": "talk_to_npc",
            "resolution_type": "social_contact",
            "target_id": target_id,
            "summary": f"Talk to NPC {target_id}",
        }

    def _map_travel_to_location(self, option: Any) -> dict:
        target_id = self._get_field(option, "target_id")
        return {
            "intent_type": "travel_to_location",
            "resolution_type": "location_travel",
            "target_id": target_id,
            "summary": f"Travel to {target_id}",
        }

    def _map_request_recap(self, option: Any) -> dict:
        return {
            "intent_type": "request_recap",
            "resolution_type": "recap",
            "target_id": None,
            "summary": "Request a recap of the current situation",
        }

    def _map_default(self, option: Any) -> dict:
        intent_type = self._get_field(option, "intent_type", "unknown")
        target_id = self._get_field(option, "target_id")
        resolution_type = self._get_field(option, "resolution_type") or intent_type
        return {
            "intent_type": intent_type,
            "resolution_type": resolution_type,
            "target_id": target_id,
            "summary": f"Perform action: {intent_type}",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_field(option: Any, field: str, default: Any = None) -> Any:
        """Read a field from an object or dict."""
        if isinstance(option, dict):
            return option.get(field, default)
        return getattr(option, field, default)
