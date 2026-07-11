from __future__ import annotations

from types import SimpleNamespace

from tests.rpg import autoplay_llm_campaign as campaign


def test_combined_background_skip_wraps_pipeline_method(monkeypatch):
    calls: list[str] = []

    class DummyPipeline:
        def submit_combined_background_llm(self, *args, **kwargs):
            calls.append("provider_submitted")
            return "job:provider"

    monkeypatch.setenv("RPG_AUTOPLAY_SKIP_COMBINED_BACKGROUND_LLM", "all")
    campaign._wrap_combined_background_llm_submit_functions(
        {"AutoplayBackgroundPipeline": DummyPipeline}
    )

    result = DummyPipeline().submit_combined_background_llm(
        provider=None,
        session_id="test-session",
        turn_index=1,
    )

    assert result == ""
    assert calls == []


def test_combined_background_skip_off_preserves_pipeline_method(monkeypatch):
    calls: list[str] = []

    class DummyPipeline:
        def submit_combined_background_llm(self, *args, **kwargs):
            calls.append("provider_submitted")
            return "job:provider"

    monkeypatch.setenv("RPG_AUTOPLAY_SKIP_COMBINED_BACKGROUND_LLM", "off")
    campaign._wrap_combined_background_llm_submit_functions(
        {"AutoplayBackgroundPipeline": DummyPipeline}
    )

    result = DummyPipeline().submit_combined_background_llm(
        provider=None,
        session_id="test-session",
        turn_index=1,
    )

    assert result == "job:provider"
    assert calls == ["provider_submitted"]


def test_foreground_skip_returns_empty_semantic_advisory(monkeypatch):
    calls: list[str] = []

    def provider_advisory(*args, **kwargs):
        calls.append("provider_called")
        return {"action_type": "provider"}

    runtime_module = SimpleNamespace(get_semantic_action_advisory=provider_advisory)
    monkeypatch.setenv("RPG_AUTOPLAY_SKIP_FOREGROUND_LLM", "all")

    installed = campaign._install_autoplay_foreground_llm_skip(runtime_module)
    result = runtime_module.get_semantic_action_advisory(player_input="travel north")

    assert installed is True
    assert result == {}
    assert calls == []


def test_foreground_skip_off_preserves_provider_advisory(monkeypatch):
    calls: list[str] = []

    def provider_advisory(*args, **kwargs):
        calls.append("provider_called")
        return {"action_type": "provider"}

    runtime_module = SimpleNamespace(get_semantic_action_advisory=provider_advisory)
    monkeypatch.setenv("RPG_AUTOPLAY_SKIP_FOREGROUND_LLM", "off")

    installed = campaign._install_autoplay_foreground_llm_skip(runtime_module)
    result = runtime_module.get_semantic_action_advisory(player_input="travel north")

    assert installed is False
    assert result == {"action_type": "provider"}
    assert calls == ["provider_called"]
