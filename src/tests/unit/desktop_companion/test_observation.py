from __future__ import annotations

from datetime import datetime, timezone

from app.desktop_companion.observation import (
    observation_fingerprint,
    parse_desktop_observation,
    redact_observation_diagnostics,
    structured_observation_prompt,
)


def captured_at() -> datetime:
    return datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_structured_observation_separates_visible_changes_and_possible_events():
    observation = parse_desktop_observation(
        """```json
        {
          "current_scene": {"value": "Inventory menu", "confidence": 0.91},
          "change_kind": "scene_change",
          "visible_changes": [{"event": "The inventory panel appeared", "confidence": 0.88, "between": [-2, 0]}],
          "possible_events": [{"event": "The user may be checking equipment", "confidence": 0.42}],
          "visible_text": ["Inventory"],
          "uncertainties": ["No selected item is clearly visible"],
          "importance": 0.66
        }
        ```""",
        observation_id="obs-1",
        session_id="chat-1",
        capture_generation="capture-1",
        source_fingerprint="screen-1",
        client_sequence=3,
        captured_at=captured_at(),
        diagnostics={"model": "vision-model", "image_data_url": "secret", "latency_ms": 120},
    )

    assert observation.current_scene.value == "Inventory menu"
    assert observation.change_kind == "scene_change"
    assert observation.visible_changes[0].between == (-2.0, 0.0)
    assert observation.possible_events[0].confidence == 0.42
    assert observation.diagnostics == {"model": "vision-model", "latency_ms": 120}
    assert observation.visible_changes[0].fingerprint == observation_fingerprint(
        "The inventory panel appeared", prefix="change"
    )


def test_plain_text_fallback_remains_uncertain_and_bounded():
    observation = parse_desktop_observation(
        "The screen appears to show a settings panel.",
        observation_id="obs-2",
        session_id="chat-1",
        capture_generation="capture-1",
        source_fingerprint="screen-1",
        client_sequence=4,
        captured_at=captured_at(),
    )

    assert observation.plain_text_fallback == "The screen appears to show a settings panel."
    assert observation.current_scene.confidence == 0.35
    assert observation.uncertainties


def test_diagnostics_recursively_remove_frame_bearing_values():
    assert redact_observation_diagnostics(
        {
            "model": "vision",
            "request_payload": {"base64": "secret"},
            "nested": {"latency": 12, "frame_count": 2},
        }
    ) == {"model": "vision", "nested": {"latency": 12}}


def test_structured_prompt_reinforces_untrusted_screen_text_boundary():
    prompt = structured_observation_prompt("What changed?")
    assert "JSON object only" in prompt
    assert "untrusted observed content" in prompt
    assert "Do not invent causes" in prompt
