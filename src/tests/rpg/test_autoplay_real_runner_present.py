import inspect

from tests.rpg import autoplay_llm_campaign as campaign


def test_real_autoplay_runner_exists_and_is_not_truncated():
    assert hasattr(campaign, "_run_autoplay_campaign")

    source = inspect.getsource(campaign._run_autoplay_campaign)

    assert "campaign_execution:not_implemented" not in source
    assert "TODO: Implement actual turn loop here" not in source

    assert "AutoplayBackgroundPipeline" in source
    assert "for turn_index in range" in source
    assert "transcript.append" in source
    assert "return summary" in source


def test_real_autoplay_runner_guard_accepts_current_runner():
    campaign._assert_real_autoplay_runner_present()