from tests.rpg.autoplay.base_runtime_response import (
    build_autoplay_base_response,
    build_deterministic_base_response,
    classify_autoplay_action,
    infer_target_npc,
    is_echo_narration,
)


def test_classify_autoplay_action_social():
    assert classify_autoplay_action("I ask Bran about the witness.") == "social"


def test_infer_target_npc_bran():
    assert infer_target_npc("I ask Bran about the witness.", {}) == "Bran"


def test_echo_narration_detection():
    assert is_echo_narration(
        player_action="I ask Bran about the witness.",
        narration="I ask Bran about the witness.",
    )


def test_deterministic_base_response_gives_bran_line():
    payload = build_deterministic_base_response(
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_index=1,
    )

    assert payload["source"] == "deterministic_base_runtime_response"
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"]
    assert payload["narration"] != "I ask Bran about the witness."
    assert payload["authoritative_changes"] is False


def test_autoplay_base_response_falls_back_to_deterministic_without_provider():
    payload = build_autoplay_base_response(
        provider=None,
        player_action="I talk to the local patron about the bandit.",
        simulation_state={},
        turn_index=2,
        use_provider=True,
    )

    assert payload["source"] == "deterministic_base_runtime_response"
    assert payload["npc"]["speaker"] == "Local Patron"