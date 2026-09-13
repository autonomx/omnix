from __future__ import annotations


def _session() -> dict:
    return {
        "manifest": {"id": "fast_visible_test", "session_id": "fast_visible_test"},
        "simulation_state": {
            "player_state": {"location_id": "tavern", "present_npc_ids": ["bran"]},
            "current_scene": {
                "scene_id": "rusty_flagon",
                "location_id": "tavern",
                "location_name": "Rusty Flagon Tavern",
                "present_npc_ids": ["bran"],
            },
            "npc_index": {
                "bran": {
                    "id": "bran",
                    "name": "Bran",
                    "role": "innkeeper",
                    "location_id": "tavern",
                    "personality_profile": {
                        "speech_examples": ["Keep your boots near the fire and your ears open."],
                    },
                }
            },
        },
        "runtime_state": {"tick": 4},
    }


def test_fast_visible_dialogue_skips_foreground_llm(monkeypatch) -> None:
    from app.rpg.session.fast_visible_dialogue_hook import install_fast_visible_dialogue_hook
    from app.rpg.session.visible_response_runtime_hook import install_visible_response_runtime_guard
    from app.rpg.session import interactive_first_call_runtime as runtime

    install_fast_visible_dialogue_hook()
    install_visible_response_runtime_guard()

    def fail_gateway():  # pragma: no cover - this should never run
        raise AssertionError("foreground semantic LLM should not be called for fast visible dialogue")

    monkeypatch.setattr(runtime, "build_app_llm_gateway", fail_gateway)

    result = runtime.apply_turn(
        "fast_visible_test",
        "Bran, how are you?",
        performance_override={"fast_visible_dialogue": True},
        session_override=_session(),
    )

    assert result["ok"] is True
    assert result["fast_visible_dialogue"] is True
    assert result["llm_called"] is False
    assert result["llm_purpose"] == "fast_visible_dialogue_safe_fallback"
    assert result["manual_turn_stage_timing"]["pre_runtime_intent_llm_ms"] == 0.0
    assert result["manual_turn_stage_timing"]["fast_visible_dialogue_ms"] >= 0.0
    assert result["visible_text"].startswith("Bran: ")
    assert "decent day" in result["visible_text"]


def test_fast_visible_dialogue_handles_rumor_question_without_facts(monkeypatch) -> None:
    from app.rpg.session.fast_visible_dialogue_hook import install_fast_visible_dialogue_hook
    from app.rpg.session.visible_response_runtime_hook import install_visible_response_runtime_guard
    from app.rpg.session import interactive_first_call_runtime as runtime

    install_fast_visible_dialogue_hook()
    install_visible_response_runtime_guard()

    def fail_gateway():  # pragma: no cover - this should never run
        raise AssertionError("foreground semantic LLM should not be called for rumor safe fallback")

    monkeypatch.setattr(runtime, "build_app_llm_gateway", fail_gateway)

    result = runtime.apply_turn(
        "fast_visible_test",
        "I ask Bran, any rumors lately?",
        performance_override={"fast_visible_dialogue": True},
        session_override=_session(),
    )

    assert result["ok"] is True
    assert result["fast_visible_dialogue"] is True
    assert result["llm_called"] is False
    assert result["manual_turn_stage_timing"]["pre_runtime_intent_llm_ms"] == 0.0
    assert result["visible_text"].startswith("Bran: Rumors come in with road dust")
    assert "strange lights" not in result["visible_text"].lower()
    assert "baroness" not in result["visible_text"].lower()


def test_fast_visible_dialogue_can_be_disabled(monkeypatch) -> None:
    from app.rpg.session.fast_visible_dialogue_hook import install_fast_visible_dialogue_hook
    from app.rpg.session import interactive_first_call_runtime as runtime

    install_fast_visible_dialogue_hook()
    calls = {"gateway": 0}

    class _Gateway:
        def complete(self, prompt: str) -> str:
            calls["gateway"] += 1
            return "{}"

    monkeypatch.setattr(runtime, "build_app_llm_gateway", lambda: _Gateway())
    runtime.apply_turn(
        "fast_visible_test",
        "Bran, how are you?",
        performance_override={"fast_visible_dialogue": False, "narration_mode": "deterministic"},
        session_override=_session(),
    )

    assert calls["gateway"] == 1
