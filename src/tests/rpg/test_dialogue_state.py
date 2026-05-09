from app.rpg.dialogue_state import (
    get_dialogue_context,
    infer_dialogue_topic,
    update_dialogue_state,
)


def test_dialogue_topic_inference_for_cloaked_traveler():
    assert infer_dialogue_topic("I ask Bran what he saw about the cloaked traveler.") == "cloaked_traveler"


def test_dialogue_state_tracks_repeat_count():
    state = {}
    action = "I ask Bran what he saw about the cloaked traveler."
    ctx1 = get_dialogue_context(state, npc_id="Bran", player_action=action)
    assert ctx1["is_repeat"] is False

    update_dialogue_state(
        state,
        npc_id="Bran",
        player_action=action,
        npc_line="They left by the side door.",
        facts_revealed=["The cloaked traveler left through the tavern side door."],
    )
    ctx2 = get_dialogue_context(state, npc_id="Bran", player_action=action)
    assert ctx2["is_repeat"] is True
    assert ctx2["repeat_count"] >= 1
    assert "side door" in ctx2["last_npc_answer"]