"""Phase 10 — Presentation layer unit tests."""
from app.rpg.presentation import (
    build_deterministic_dialogue_fallback,
    build_deterministic_scene_fallback,
    build_dialogue_presentation_payload,
    build_personality_prompt_hints,
    build_personality_style_tags,
    build_personality_summary,
    build_scene_presentation_payload,
    ensure_personality_state,
    get_actor_personality_profile,
)
from app.rpg.presentation.dialogue_prompt_builder import build_dialogue_llm_payload
from app.rpg.presentation.speaker_cards import (
    build_party_speaker_cards,
    build_speaker_cards,
)


def test_build_personality_style_tags_returns_deterministic_tags():
    actor = {"npc_id": "npc_a", "name": "A", "loyalty": 0.8, "morale": 0.9, "role": "support"}
    one = build_personality_style_tags(actor)
    two = build_personality_style_tags(actor)
    assert one == two


def test_build_personality_style_tags_loyalty_cold():
    actor = {"npc_id": "npc_a", "loyalty": -0.5, "morale": 0.5, "role": "ally"}
    tags = build_personality_style_tags(actor)
    assert "cold" in tags


def test_build_personality_style_tags_role_guard():
    actor = {"npc_id": "npc_a", "loyalty": 0.0, "morale": 0.5, "role": "guard"}
    tags = build_personality_style_tags(actor)
    assert "protective" in tags


def test_build_personality_prompt_hints():
    actor = {"npc_id": "npc_b", "name": "Bob", "loyalty": 0.0, "morale": 0.5, "role": "ally"}
    hints = build_personality_prompt_hints(actor)
    assert hints["name"] == "Bob"
    assert "speech_guidance" in hints


def test_ensure_personality_state():
    sim = {"presentation_state": {"personality_state": {"profiles": {"npc_1": {"actor_id": "npc_1", "display_name": "NPC One"}}}}}
    result = ensure_personality_state(sim)
    assert "presentation_state" in result
    profiles = result["presentation_state"]["personality_state"]["profiles"]
    assert "npc_1" in profiles


def test_get_actor_personality_profile():
    sim = {"presentation_state": {"personality_state": {"profiles": {}}}}
    profile = get_actor_personality_profile(sim, "new_actor", default_name="New Actor")
    assert profile["actor_id"] == "new_actor"
    assert profile["display_name"] == "New Actor"


def test_build_personality_summary():
    sim = {"presentation_state": {"personality_state": {"profiles": {"a": {}, "b": {}}}}}
    summary = build_personality_summary(sim)
    assert summary["profile_count"] == 2


def test_build_speaker_cards_includes_player():
    simulation_state = {"player_state": {"party_state": {"companions": []}}}
    cards = build_speaker_cards(simulation_state, {"scene_id": "scene_gate"})
    assert any(card.get("speaker_id") == "player" for card in cards)


def test_scene_presentation_payload_has_expected_keys():
    simulation_state = {"player_state": {"party_state": {"companions": []}}}
    payload = build_scene_presentation_payload(simulation_state, {"scene_id": "scene_1", "tone": "tense"})
    assert "speaker_cards" in payload
    assert "companion_interjections" in payload
    assert "companion_reactions" in payload


def test_dialogue_presentation_payload_has_expected_keys():
    simulation_state = {"player_state": {"party_state": {"companions": []}}}
    payload = build_dialogue_presentation_payload(simulation_state, {"dialogue_id": "dlg_1", "speaker_id": "npc_x"})
    assert "speaker_cards" in payload
    assert "dialogue_context" in payload


def test_deterministic_dialogue_fallback_warm():
    result = build_deterministic_dialogue_fallback({"display_name": "Alice", "tone": "warm"}, {"topic": "peace"})
    assert "Alice" in result["text"]
    assert result["source"] == "deterministic_fallback"


def test_deterministic_dialogue_fallback_stern():
    result = build_deterministic_dialogue_fallback({"display_name": "Bob", "tone": "stern"}, {"topic": "war"})
    assert "Bob" in result["text"]
    assert "stern" not in result["text"].lower() or "firm" in result["text"].lower()


def test_deterministic_scene_fallback_tense():
    result = build_deterministic_scene_fallback({"tone": "tense", "location_id": "castle"})
    assert "castle" in result["text"]
    assert "Tension" in result["text"]


def test_deterministic_scene_fallback_calm():
    result = build_deterministic_scene_fallback({"tone": "calm", "location_id": "garden"})
    assert "garden" in result["text"]
    assert "quieter" in result["text"]


def test_dialogue_llm_payload_history_is_deterministic():
    simulation_state = {"presentation_state": {"personality_state": {"profiles": {}}}}
    dialogue_state = {
        "scene_id": "scene_1",
        "location_id": "loc_1",
        "topic": "trade",
        "transcript": [
            {"speaker": "npc_b", "text": "Second"},
            {"speaker": "npc_a", "text": "First"},
        ],
    }
    payload = build_dialogue_llm_payload(simulation_state, dialogue_state, "npc_a", actor_name="A")
    history = payload["dialogue_context"]["history"]
    assert history == [
        {"speaker": "npc_a", "text": "First"},
        {"speaker": "npc_b", "text": "Second"},
    ]


def test_speaker_cards_keep_player_first():
    simulation_state = {
        "player_state": {
            "party_state": {
                "companions": [
                    {"npc_id": "npc_b", "name": "B", "status": "active", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
                ]
            }
        }
    }
    cards = build_speaker_cards(simulation_state, {"scene_id": "scene_1"})
    assert cards[0]["speaker_id"] == "player"


def test_build_party_speaker_cards_skips_inactive():
    companions = [
        {"npc_id": "npc_a", "name": "A", "status": "active", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
        {"npc_id": "npc_b", "name": "B", "status": "downed", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
    ]
    cards = build_party_speaker_cards({}, companions)
    ids = [card["speaker_id"] for card in cards]
    assert "npc_a" in ids
    assert "npc_b" not in ids


def test_personality_profile_lazy_creation():
    simulation_state = {"presentation_state": {"personality_state": {"profiles": {}}}}
    profile = get_actor_personality_profile(simulation_state, "npc_new", default_name="New NPC")
    assert profile["actor_id"] == "npc_new"
    assert profile["display_name"] == "New NPC"
    profiles = simulation_state["presentation_state"]["personality_state"]["profiles"]
    assert "npc_new" in profiles
