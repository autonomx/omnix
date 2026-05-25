from __future__ import annotations

from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_Q_FRAGMENT = _PARTS_DIR / "zz_bundle_q_1000_turn_preflight_profile.pyfrag"
_S_FRAGMENT = _PARTS_DIR / "zz_bundle_s_live_1000_run_profile.pyfrag"
_AC_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ac_1000_profile_loop_guard.pyfrag"
_AD_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ad_1000_profile_smoke100_graph_alignment.pyfrag"


def _load_q_s_ac_ad_namespace():
    namespace = {"__name__": "_bundle_ad_1000_profile_smoke100_graph_alignment_test"}
    for fragment in (_Q_FRAGMENT, _S_FRAGMENT, _AC_FRAGMENT, _AD_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def _assert_smoke100_graph_args(argv: list[str]):
    assert "--player-agent" in argv
    assert argv[argv.index("--player-agent") + 1] == "llm"
    assert "--player-agent-context-mode" in argv
    assert argv[argv.index("--player-agent-context-mode") + 1] == "compact"
    assert "--player-agent-cache" in argv
    assert argv[argv.index("--player-agent-cache") + 1] == "on"
    assert "--scenario-seed" in argv
    assert argv[argv.index("--scenario-seed") + 1] == "tavern_story_seed"
    assert "--latency-profile" in argv
    assert argv[argv.index("--latency-profile") + 1] == "playable"
    assert "--strategy" in argv
    assert argv[argv.index("--strategy") + 1] == "goal_directed_quest_runner"
    assert "--autoplay-base-response" in argv
    assert argv[argv.index("--autoplay-base-response") + 1] == "deterministic"
    assert "--deferred-advisory-promotion" in argv
    assert argv[argv.index("--deferred-advisory-promotion") + 1] == "on"
    assert "--checkpoint-mode" in argv
    assert argv[argv.index("--checkpoint-mode") + 1] == "background"
    assert "--player-agent-goal-pressure" in argv
    assert "--player-agent-goal-pressure-repair" in argv
    assert "--goal-pressure-no-change-threshold" in argv
    assert argv[argv.index("--goal-pressure-no-change-threshold") + 1] == "8"
    assert "--goal-pressure-passive-rate-threshold" in argv
    assert argv[argv.index("--goal-pressure-passive-rate-threshold") + 1] == "0.45"
    assert "--max-objective-target-no-progress-streak" in argv
    assert argv[argv.index("--max-objective-target-no-progress-streak") + 1] == "8"
    assert "--pre-turn-advisory-fast-path" in argv
    assert "--pre-turn-advisory-carry-candidate-limit" in argv
    assert argv[argv.index("--pre-turn-advisory-carry-candidate-limit") + 1] == "12"
    assert "--pre-turn-advisory-carry-accepted-limit" in argv
    assert argv[argv.index("--pre-turn-advisory-carry-accepted-limit") + 1] == "20"
    assert "--force-exit-after-artifacts-on-background-timeout" in argv


def test_bundle_ad_patches_preflight_and_live_commands_with_smoke100_graph_controls():
    namespace = _load_q_s_ac_ad_namespace()

    preflight_command = namespace["_bundle_q_build_preflight_command"]()
    live_command = namespace["_bundle_s_build_live_command"]()

    _assert_smoke100_graph_args(preflight_command)
    _assert_smoke100_graph_args(live_command)
    # Bundle AC loop guard should remain present after AD alignment.
    assert "--stop-on-loop" in preflight_command
    assert "--max-repeated-actions" in preflight_command
    assert "--stop-on-loop" in live_command
    assert "--max-repeated-actions" in live_command


def test_bundle_ad_profile_expansion_preserves_caller_strategy_and_seed_overrides():
    namespace = _load_q_s_ac_ad_namespace()

    expanded = namespace["_bundle_q_append_missing_profile_args"]([
        "--strategy", "custom_strategy",
        "--scenario-seed", "custom_seed",
        "--player-agent", "scripted",
    ])

    assert expanded[expanded.index("--strategy") + 1] == "custom_strategy"
    assert expanded[expanded.index("--scenario-seed") + 1] == "custom_seed"
    assert expanded[expanded.index("--player-agent") + 1] == "scripted"
    assert "--player-agent-context-mode" in expanded
    assert expanded[expanded.index("--player-agent-context-mode") + 1] == "compact"
    assert "--goal-pressure-no-change-threshold" in expanded
    assert expanded[expanded.index("--goal-pressure-no-change-threshold") + 1] == "8"
    assert "--stop-on-loop" in expanded


def test_bundle_ad_missing_command_flags_include_graph_alignment_flags():
    namespace = _load_q_s_ac_ad_namespace()

    missing = namespace["_bundle_q_missing_command_flags"](["--turns", "1000"])

    assert "--player-agent" in missing
    assert "--player-agent-context-mode" in missing
    assert "--scenario-seed" in missing
    assert "--strategy" in missing
    assert "--player-agent-goal-pressure" in missing
    assert "--player-agent-goal-pressure-repair" in missing
    assert "--max-objective-target-no-progress-streak" in missing
    assert "--pre-turn-advisory-fast-path" in missing
    assert "--stop-on-loop" in missing


def test_bundle_ad_profile_metadata_records_smoke100_graph_defaults():
    namespace = _load_q_s_ac_ad_namespace()

    for profile_name in ("_BUNDLE_Q_PROFILE", "_BUNDLE_S_PROFILE"):
        defaults = namespace[profile_name]["defaults"]
        assert defaults["player_agent"] == "llm"
        assert defaults["player_agent_context_mode"] == "compact"
        assert defaults["player_agent_cache"] == "on"
        assert defaults["scenario_seed"] == "tavern_story_seed"
        assert defaults["latency_profile"] == "playable"
        assert defaults["strategy"] == "goal_directed_quest_runner"
        assert defaults["autoplay_base_response"] == "deterministic"
        assert defaults["goal_pressure_enabled"] is True
        assert defaults["goal_pressure_repair_enabled"] is True
        assert defaults["max_objective_target_no_progress_streak"] == 8
        assert defaults["pre_turn_advisory_fast_path"] is True
