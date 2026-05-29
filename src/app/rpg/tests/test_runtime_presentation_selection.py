from app.rpg.session.runtime import _select_final_visible_presentation


def test_combat_narration_beats_deferred_runtime_fallback():
    selected = _select_final_visible_presentation(
        {
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "combat_narration_payload": {
                "narration": "Your sword strike lands; the Bandit loses 1 HP.",
                "npc": {"speaker": "", "line": ""},
            },
            "combat_narration_validation": {"ok": True},
        },
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The confrontation remains tense, but no injury is resolved.",
        },
        prior_narration="The confrontation remains tense, but no injury is resolved.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selected["source"] == "combat_narration"
    assert selected["llm_called"] is True
    assert "loses 1 HP" in selected["narration"]


def test_authoritative_runtime_result_beats_deferred_runtime_fallback_for_noncombat():
    selected = _select_final_visible_presentation(
        {},
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The moment responds without producing a major new consequence.",
        },
        prior_narration="Bran lists the available provisions: Hot stew -- 1 silver, 5 copper.",
        prior_npc={"speaker": "Bran", "line": "I can offer Hot stew."},
        prior_llm_called=False,
    )

    assert selected["source"] == "authoritative_runtime_result"
    assert selected["llm_called"] is False
    assert "Hot stew" in selected["narration"]
    assert selected["npc"]["speaker"] == "Bran"


def test_valid_provider_runtime_narration_beats_prior_noncombat_result():
    selected = _select_final_visible_presentation(
        {},
        runtime_narration_payload={
            "source": "provider_runtime_narration",
            "narration": "Bran leans closer and lowers his voice.",
            "npc": {"speaker": "Bran", "line": "Tell me exactly what you found."},
        },
        prior_narration="The moment responds without producing a major new consequence.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selected["source"] == "provider_runtime_narration"
    assert selected["llm_called"] is True
    assert selected["narration"] == "Bran leans closer and lowers his voice."


def test_direct_companion_response_beats_deferred_runtime_fallback():
    selected = _select_final_visible_presentation(
        {
            "direct_companion_turn_result": {
                "matched": True,
                "name": "Bran",
                "line": 'Bran stays close. "I\'m with you."',
            },
        },
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The moment responds without producing a major new consequence.",
        },
        prior_narration="The moment responds without producing a major new consequence.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selected["source"] == "direct_companion_response"
    assert selected["llm_called"] is False
    assert selected["npc"]["speaker"] == "Bran"
    assert "stays close" in selected["narration"]


def test_command_echo_does_not_beat_deferred_runtime_fallback():
    selected = _select_final_visible_presentation(
        {
            "turn_contract": {
                "player_input": "I travel north toward the old mill.",
            },
        },
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The scene shifts with the movement toward the old mill road.",
        },
        prior_narration="I travel north toward the old mill.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selected["source"] == "deferred_runtime_narration_pending"
    assert "old mill road" in selected["narration"]


def test_low_level_failure_placeholder_does_not_beat_deferred_runtime_fallback():
    selected = _select_final_visible_presentation(
        {},
        runtime_narration_payload={
            "source": "deferred_runtime_narration_pending",
            "narration": "The moment responds without producing a major new consequence.",
        },
        prior_narration="Result: You cannot find that object here.",
        prior_npc={},
        prior_llm_called=False,
    )

    assert selected["source"] == "deferred_runtime_narration_pending"
    assert selected["narration"] == "The moment responds without producing a major new consequence."
