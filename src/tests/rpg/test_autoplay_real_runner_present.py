import inspect

from tests.rpg.autoplay_llm_campaign import (
    _assert_real_autoplay_runner_present,
    _run_autoplay_campaign,
)


def test_real_runner_contains_finalization_block():
    _assert_real_autoplay_runner_present()

    source = inspect.getsource(_run_autoplay_campaign)

    assert "write_results_zip.start" in source
    assert "write_results_zip.end" in source
    assert "summary[\"artifact_paths\"]" in source
    assert "_force_exit_if_background_threads_remain" in source
    assert "return summary" in source


def test_no_placeholder_run_campaign_autoplay_exists():
    import tests.rpg.autoplay_llm_campaign as mod

    assert not hasattr(mod, "_run_campaign_autoplay")
