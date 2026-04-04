"""Phase 8.0 — UX Presenters.

UI-safe presentation of UX payloads.  Returns stable, whitelisted
fields only — no raw metadata passthrough.
"""

from __future__ import annotations


class UXPresenter:
    """UI-safe presenter for UX-layer payloads."""

    def present_scene_payload(self, payload: dict) -> dict:
        """Present a SceneUXPayload dict for frontend consumption."""
        result = {
            "id": payload.get("payload_id"),
            "scene": payload.get("scene", {}),
            "choices": payload.get("choices", []),
            "panels": payload.get("panels", []),
            "highlights": payload.get("highlights", {}),
        }
        # Phase 8.1 — include interaction if present
        interaction = payload.get("interaction")
        if interaction:
            result["interaction"] = interaction
        # Phase 8.2 — include encounter if present
        encounter = payload.get("encounter")
        if encounter:
            result["encounter"] = encounter
        return result

    def present_action_result_payload(self, payload: dict) -> dict:
        """Present an ActionResultPayload dict for frontend consumption."""
        result = {
            "result_id": payload.get("result_id", ""),
            "action_result": payload.get("action_result", {}),
            "updated_scene": payload.get("updated_scene", {}),
            "updated_choices": [
                self.present_choice_card(c)
                for c in payload.get("updated_choices", [])
            ],
            "updated_panels": [
                self.present_panel_descriptor(p)
                for p in payload.get("updated_panels", [])
            ],
        }
        # Phase 8.1 — include interaction if present
        interaction = payload.get("interaction")
        if interaction:
            result["interaction"] = interaction
        # Phase 8.2 — include encounter if present
        encounter = payload.get("encounter")
        if encounter:
            result["encounter"] = encounter
        return result

    def present_choice_card(self, card: dict) -> dict:
        """Present a single PlayerChoiceCard dict."""
        return {
            "choice_id": card.get("choice_id", ""),
            "label": card.get("label", ""),
            "summary": card.get("summary", ""),
            "intent_type": card.get("intent_type", ""),
            "target_id": card.get("target_id"),
            "tags": list(card.get("tags", [])),
            "priority": card.get("priority", 0.0),
        }

    def present_panel_descriptor(self, descriptor: dict) -> dict:
        """Present a single PanelDescriptor dict."""
        return {
            "panel_id": descriptor.get("panel_id", ""),
            "title": descriptor.get("title", ""),
            "panel_type": descriptor.get("panel_type", ""),
            "count": descriptor.get("count"),
        }
