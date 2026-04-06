"""Phase A — Character UI builder regression tests.

Ensures the character UI system does not break existing functionality:
- Existing presentation routes still return expected data
- Speaker cards are not mutated by character_ui_state integration
- Ensure personality state still works as before
- Backward compatibility with old saves (missing states)
"""
import copy

from app.rpg.presentation.personality_state import (
    build_personality_summary,
    ensure_personality_state,
    get_actor_personality_profile,
)
from app.rpg.ui.character_builder import build_character_ui_state


def test_speaker_cards_not_mutated_by_character_ui():
    """Speaker cards in simulation_state are not mutated by character UI state."""
    original_speaker_cards = [
        {"entity_id": "npc:a", "speaker_name": "A", "speaker_order": 1},
        {"entity_id": "npc:b", "speaker_name": "B", "speaker_order": 2},
    ]
    simulation_state = {
        "presentation_state": {
            "speaker_cards": original_speaker_cards,
        }
    }
    # Deep copy to detect mutations
    original_copy = copy.deepcopy(simulation_state)

    # Build character UI state
    result = build_character_ui_state(simulation_state)
    assert result["count"] == 2

    # Verify speaker_cards were not mutated
    assert simulation_state["presentation_state"]["speaker_cards"] == original_copy["presentation_state"]["speaker_cards"]


def test_ensure_personality_state_still_returns_profiles():
    """ensure_personality_state still returns normalized profiles as before."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:a": {"actor_id": "npc:a", "display_name": "A", "tone": "warm"},
                }
            }
        }
    }

    result = ensure_personality_state(simulation_state)
    profiles = result["presentation_state"]["personality_state"]["profiles"]
    assert "npc:a" in profiles
    assert profiles["npc:a"]["tone"] == "warm"
    assert profiles["npc:a"]["display_name"] == "A"


def test_get_actor_personality_profile_still_works():
    """get_actor_personality_profile still works with existing profiles."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:a": {"actor_id": "npc:a", "display_name": "A", "tone": "neutral"},
                }
            }
        }
    }

    profile = get_actor_personality_profile(simulation_state, "npc:a")
    assert profile["actor_id"] == "npc:a"
    assert profile["display_name"] == "A"
    assert profile["tone"] == "neutral"


def test_build_personality_summary_still_works():
    """build_personality_summary still returns correct counts."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {"a": {}, "b": {}, "c": {}}
            }
        }
    }

    summary = build_personality_summary(simulation_state)
    assert summary["profile_count"] == 3
    assert summary["actor_ids"] == ["a", "b", "c"]


def test_backward_compat_empty_simulation_state():
    """Empty simulation state does not break any function."""
    simulation_state = {}

    # ensure_personality_state should work
    result = ensure_personality_state(simulation_state)
    assert "presentation_state" in result

    # build_character_ui_state should work
    ui_result = build_character_ui_state(simulation_state)
    assert ui_result == {"characters": [], "count": 0}


def test_backward_compat_missing_personality_state():
    """Missing personality_state in presentation_state does not break functions."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:x", "speaker_name": "X"}]
        }
    }

    # build_character_ui_state should not crash
    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["id"] == "npc:x"
    assert result["characters"][0]["personality"]["tone"] == ""


def test_character_ui_does_not_overwrite_existing_presentation():
    """Character UI state is additive and does not overwrite existing presentation data."""
    from app.rpg.api.rpg_presentation_routes import _ensure_character_ui_state

    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {"npc:a": {"actor_id": "npc:a", "display_name": "A"}},
            },
            "speaker_cards": [{"entity_id": "npc:a", "speaker_name": "A"}],
            "some_other_key": {"existing": "data"},
        },
        "ai_state": {
            "npc_minds": {"npc:a": {"current_intent": "test"}},
        },
    }
    original_copy = copy.deepcopy(simulation_state["presentation_state"])

    ensure_personality_state(simulation_state)
    _ensure_character_ui_state(simulation_state)

    # Original data should still be present
    assert simulation_state["presentation_state"]["some_other_key"]["existing"] == "data"

    # Character UI state should be added at the presentation boundary
    assert "character_ui_state" in simulation_state["presentation_state"]

    # Original speaker_cards should not be modified
    assert simulation_state["presentation_state"]["speaker_cards"] == original_copy["speaker_cards"]


def test_deterministic_output_across_multiple_calls():
    """Multiple calls produce identical output (determinism check)."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:a": {"tone": "warm", "style_tags": ["friendly"]},
                    "npc:b": {"tone": "cold", "style_tags": ["serious"]},
                }
            },
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "Alpha", "speaker_order": 1},
                {"entity_id": "npc:b", "speaker_name": "Beta", "speaker_order": 2},
            ],
        },
        "social_state": {
            "relationships": {
                "npc:a": {"npc:b": {"kind": "ally", "score": 0.7}},
                "npc:b": {"npc:a": {"kind": "ally", "score": 0.7}},
            }
        },
    }

    results = [build_character_ui_state(simulation_state) for _ in range(5)]
    for i in range(1, len(results)):
        assert results[i] == results[0], f"Run {i} differs from run 0"


# ---- Phase 11.2 — Inspector regression tests ----


def test_inspector_does_not_mutate_simulation_state():
    """build_character_inspector_state does not mutate the input simulation state."""
    from app.rpg.ui.character_builder import build_character_inspector_state

    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "A", "speaker_order": 1},
            ]
        },
    }
    original_copy = copy.deepcopy(simulation_state)

    result = build_character_inspector_state(simulation_state)
    assert result["count"] == 1

    # Verify simulation_state was not mutated
    assert simulation_state == original_copy


def test_inspector_backward_compat_empty_simulation_state():
    """Empty simulation state does not break inspector functions."""
    from app.rpg.ui.character_builder import build_character_inspector_state

    result = build_character_inspector_state({})
    assert result == {"characters": [], "count": 0}


def test_inspector_deterministic_output():
    """Multiple calls to build_character_inspector_state produce identical output."""
    from app.rpg.ui.character_builder import build_character_inspector_state

    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "Alpha", "speaker_order": 1},
                {"entity_id": "npc:b", "speaker_name": "Beta", "speaker_order": 2},
            ],
        },
    }

    results = [build_character_inspector_state(simulation_state) for _ in range(5)]
    for i in range(1, len(results)):
        assert results[i] == results[0], f"Inspector run {i} differs from run 0"


def test_inspector_does_not_break_personality_state():
    """ensure_personality_state still works after adding inspector."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:a": {"actor_id": "npc:a", "display_name": "A", "tone": "warm"},
                }
            },
            "speaker_cards": [{"entity_id": "npc:a", "speaker_name": "A"}],
        }
    }

    # Calling ensure_personality_state should still work
    result = ensure_personality_state(simulation_state)
    profiles = result["presentation_state"]["personality_state"]["profiles"]
    assert "npc:a" in profiles


def test_inspector_does_not_break_character_ui_state():
    """build_character_ui_state still works after adding inspector functions."""
    from app.rpg.ui.character_builder import build_character_ui_state

    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "A", "speaker_order": 1},
            ]
        },
    }

    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["id"] == "npc:a"
    assert result["characters"][0]["name"] == "A"


def test_inspector_relationship_summary_backward_compat():
    """Relationship summary handles empty relationships gracefully."""
    from app.rpg.ui.character_builder import build_character_inspector_entry

    simulation_state = {
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:x", "speaker_name": "X"}],
        }
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    summary = result["inspector"]["relationship_summary"]
    assert summary["positive"] == 0
    assert summary["negative"] == 0
    assert summary["neutral"] == 0
