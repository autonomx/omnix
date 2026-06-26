from __future__ import annotations


def test_diegetic_fallback_replaces_generic_for_meaningful_roleplay(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.diegetic_fallback_hook import install_diegetic_fallback_hook

    monkeypatch.delattr(runtime, "_omnix_diegetic_fallback_hook_installed", raising=False)

    def generic_only(*, speaker: str, profile: dict, player_input: str) -> tuple[str, str]:
        return "general_dialogue", "Ask that plainly again, and I will answer as best I can."

    monkeypatch.setattr(runtime, "_safe_dialogue_fallback_line", generic_only)
    install_diegetic_fallback_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={"role": "innkeeper"},
        player_input="i scream nonsense at the wall",
    )

    assert topic == "diegetic_reaction"
    assert "command failure" in line.lower()
    assert "ask that plainly again" not in line.lower()


def test_diegetic_fallback_keeps_generic_for_client_noise(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.diegetic_fallback_hook import install_diegetic_fallback_hook

    monkeypatch.delattr(runtime, "_omnix_diegetic_fallback_hook_installed", raising=False)

    def generic_only(*, speaker: str, profile: dict, player_input: str) -> tuple[str, str]:
        return "general_dialogue", "Ask that plainly again, and I will answer as best I can."

    monkeypatch.setattr(runtime, "_safe_dialogue_fallback_line", generic_only)
    install_diegetic_fallback_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={"role": "innkeeper"},
        player_input="[object Object]",
    )

    assert topic == "general_dialogue"
    assert line == "Ask that plainly again, and I will answer as best I can."


def test_diegetic_fallback_preserves_specific_existing_fallback(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.diegetic_fallback_hook import install_diegetic_fallback_hook

    monkeypatch.delattr(runtime, "_omnix_diegetic_fallback_hook_installed", raising=False)

    def specific(*, speaker: str, profile: dict, player_input: str) -> tuple[str, str]:
        return "rumor_inquiry", "I hear pieces of news, but I trust only some of them."

    monkeypatch.setattr(runtime, "_safe_dialogue_fallback_line", specific)
    install_diegetic_fallback_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={"role": "innkeeper"},
        player_input="any rumors?",
    )

    assert topic == "rumor_inquiry"
    assert line == "I hear pieces of news, but I trust only some of them."
