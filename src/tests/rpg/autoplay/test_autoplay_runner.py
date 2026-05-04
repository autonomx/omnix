from argparse import Namespace
from pathlib import Path

from tests.rpg.autoplay_llm_campaign import run_autoplay_campaign


def test_autoplay_runner_fallback_executes_short_campaign(tmp_path: Path, monkeypatch):
    state_holder = {"state": {}}

    def fake_prepare(*, session_id, simulation_state, reset_session_state=True):
        state_holder["state"] = dict(simulation_state)
        return {"session_id": session_id, "simulation_state": state_holder["state"]}

    def fake_load_state(session_id):
        return dict(state_holder["state"])

    def fake_turn(*, session_id, player_action, turn_index):
        state_holder["state"]["turns"] = int(state_holder["state"].get("turns") or 0) + 1
        return {
            "ok": True,
            "runtime_name": "manual_harness._run_one_manual_turn",
            "simulation_state": dict(state_holder["state"]),
            "turn_contract": {"player_action": player_action},
            "narration": "You advance the autoplay test.",
        }

    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign.prepare_autoplay_manual_session", fake_prepare)
    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign.load_autoplay_simulation_state", fake_load_state)
    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign._call_turn_runtime", fake_turn)

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
        base_url="http://127.0.0.1:5000",
        start_app_server=False,
        server_startup_timeout=1,
        max_repeated_actions=5,
        max_no_progress_turns=0,
        stop_on_loop=False,
        fail_on_runtime_error=False,
        fail_on_compatibility_turn_runtime=True,
        max_player_agent_fallback_rate=1.0,
        fail_on_regression_warnings=False,
        debug_provider_shape=False,
        debug_turn_runtime_shape=False,
    )

    summary = run_autoplay_campaign(args)

    assert summary["turns_executed"] == 3
    assert summary["health"]["metrics"]["compatibility_turn_runtime_count"] == 0
    assert summary["health"]["metrics"]["real_turn_runtime_count"] == 3
    assert summary["artifact_paths"]["zip"]
    assert Path(summary["artifact_paths"]["zip"]).exists()