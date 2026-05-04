from argparse import Namespace
from pathlib import Path

from tests.rpg.autoplay_llm_campaign import run_autoplay_campaign


def test_autoplay_runner_fallback_executes_short_campaign(tmp_path: Path):
    args = Namespace(
        turns=3,
        session_id="autoplay_test_session",
        scenario_seed="tavern_story_seed",
        player_agent="fallback",
        strategy="balanced_story_player",
        player_agent_max_tokens=200,
        suggested_action_limit=12,
        artifact_detail="full",
        output_dir=str(tmp_path),
        max_repeated_actions=5,
        stop_on_loop=False,
        fail_on_runtime_error=False,
        fail_on_compatibility_turn_runtime=False,
        max_player_agent_fallback_rate=1.0,
        debug_provider_shape=False,
        fail_on_regression_warnings=False,
    )

    summary = run_autoplay_campaign(args)

    assert summary["turns_executed"] == 3
    assert summary["artifact_paths"]["zip"]
    assert Path(summary["artifact_paths"]["zip"]).exists()