from __future__ import annotations

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
