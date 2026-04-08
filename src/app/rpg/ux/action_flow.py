"""Phase 8.0 — UX Action Flow.

Formalises the player interaction flow:
  request scene → select choice → receive result → refresh panels.

This class orchestrates existing methods only — it never computes
truth itself.
"""

from __future__ import annotations

from typing import Any

from .payload_builder import UXPayloadBuilder

# Panel-id → GameLoop method-name mapping
_PANEL_METHOD_MAP: dict[str, str] = {
    "journal": "get_journal_panel",
    "recap": "get_recap_panel",
    "codex": "get_codex_panel",
    "campaign_memory": "get_campaign_memory_panel",
    "social": "get_social_dashboard",
    "arc": "get_arc_panel",
    "reveals": "get_reveal_panel",
    "packs": "list_registered_packs",
    "scene_bias": "get_scene_bias_panel",
}


class UXActionFlow:
    """Orchestrates player actions through existing engine methods."""

    def __init__(self, payload_builder: UXPayloadBuilder | None = None) -> None:
        self._payload_builder = payload_builder or UXPayloadBuilder()

    # ------------------------------------------------------------------
    # Scene & choices
    # ------------------------------------------------------------------

    def get_current_scene(self, loop: Any) -> dict:
        """Return the current scene as a presented payload dict."""
        payload = self._payload_builder.build_scene_payload(loop)
        return payload.to_dict()

    def get_current_choices(self, loop: Any) -> dict:
        """Return only the current choice cards."""
        payload = self._payload_builder.build_scene_payload(loop)
        return {
            "choices": [c.to_dict() for c in payload.choices],
        }

    # ------------------------------------------------------------------
    # Choice selection
    # ------------------------------------------------------------------

    def select_choice(self, loop: Any, choice_id: str) -> dict:
        """Select a choice and return an action-result payload dict.

        Delegates to ``loop.resolve_selected_option`` for the actual
        event-path execution, then wraps the result in a UX payload.
        """
        control = getattr(loop, "gameplay_control_controller", None)
        if control:
            choice_set = control.get_last_choice_set()
            valid_ids = {c["id"] for c in choice_set.get("options", [])}
            if choice_id not in valid_ids:
                return {"ok": False, "reason": "invalid_choice_id"}
        action_result = loop.resolve_selected_option(choice_id)
        result_payload = self._payload_builder.build_action_result_payload(
            loop, action_result
        )
        return result_payload.to_dict()

    # ------------------------------------------------------------------
    # Recap
    # ------------------------------------------------------------------

    def request_recap(self, loop: Any) -> dict:
        """Return the recap panel via the existing recap mechanism."""
        if hasattr(loop, "get_recap_panel"):
            return loop.get_recap_panel()
        return {
            "title": "Recap",
            "summary": "",
            "scene_summary": {},
            "active_threads": [],
            "recent_consequences": [],
            "social_highlights": [],
        }

    # ------------------------------------------------------------------
    # Panel routing
    # ------------------------------------------------------------------

    def open_panel(self, loop: Any, panel_id: str) -> dict:
        """Open a named panel by routing to the correct loop method.

        Returns:
            The presenter-shaped panel dict, or an error dict if the
            panel is unknown.
        """
        method_name = _PANEL_METHOD_MAP.get(panel_id)
        if method_name is None:
            return {"error": "unknown_panel", "panel_id": panel_id}
        method = getattr(loop, method_name, None)
        if method is None:
            return {"error": "panel_not_available", "panel_id": panel_id}
        return method()
