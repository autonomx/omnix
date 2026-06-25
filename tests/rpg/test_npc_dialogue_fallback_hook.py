from __future__ import annotations


def test_bran_trouble_question_has_specific_safe_fallback(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.npc_dialogue_fallback_hook import install_npc_dialogue_fallback_hook

    monkeypatch.delattr(runtime, "_omnix_npc_dialogue_fallback_hook_installed", raising=False)
    install_npc_dialogue_fallback_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={},
        player_input="i ask bran, any troubles lately?",
    )

    assert topic == "trouble_inquiry"
    assert "trouble" in line.lower()
    assert "ask that plainly again" not in line.lower()


def test_non_trouble_fallback_still_delegates_to_original_topics() -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.npc_dialogue_fallback_hook import install_npc_dialogue_fallback_hook

    install_npc_dialogue_fallback_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={},
        player_input="how are you doing?",
    )

    assert topic == "wellbeing_inquiry"
    assert "decent day" in line.lower()
