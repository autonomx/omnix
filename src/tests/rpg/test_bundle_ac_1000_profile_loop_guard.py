from __future__ import annotations

from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_Q_FRAGMENT = _PARTS_DIR / "zz_bundle_q_1000_turn_preflight_profile.pyfrag"
_S_FRAGMENT = _PARTS_DIR / "zz_bundle_s_live_1000_run_profile.pyfrag"
_AC_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ac_1000_profile_loop_guard.pyfrag"


def _load_q_s_ac_namespace():
    namespace = {"__name__": "_bundle_ac_1000_profile_loop_guard_test"}
    for fragment in (_Q_FRAGMENT, _S_FRAGMENT, _AC_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def _assert_loop_guard_args(argv: list[str]):
    assert "--stop-on-loop" in argv
    assert "--max-repeated-actions" in argv
    assert argv[argv.index("--max-repeated-actions") + 1] == "4"
    assert "--max-no-progress-turns" in argv
    assert argv[argv.index("--max-no-progress-turns") + 1] == "12"
    assert "--action-diversity-window" in argv
    assert argv[argv.index("--action-diversity-window") + 1] == "8"
    assert "--min-action-diversity-rate" in argv
    assert argv[argv.index("--min-action-diversity-rate") + 1] == "0.25"
    assert "--player-agent-anti-loop-streak-threshold" in argv
    assert argv[argv.index("--player-agent-anti-loop-streak-threshold") + 1] == "3"


def test_bundle_ac_patches_preflight_and_live_canonical_commands_with_loop_guard():
    namespace = _load_q_s_ac_namespace()

    preflight_command = namespace["_bundle_q_build_preflight_command"]()
    live_command = namespace["_bundle_s_build_live_command"]()

    _assert_loop_guard_args(preflight_command)
    _assert_loop_guard_args(live_command)
    assert "--compact-transcript-mode" not in preflight_command
    assert "--compact-transcript-mode" not in live_command
    assert "--zip-results" not in live_command


def test_bundle_ac_profile_expansion_adds_loop_guard_without_overriding_caller_values():
    namespace = _load_q_s_ac_namespace()

    preflight = namespace["_bundle_q_append_missing_profile_args"]([
        "--turns", "777",
        "--max-repeated-actions", "9",
    ])
    live = namespace["_bundle_s_append_missing_profile_args"]([
        "--turns", "888",
        "--max-no-progress-turns", "30",
    ])

    assert preflight[preflight.index("--turns") + 1] == "777"
    assert preflight[preflight.index("--max-repeated-actions") + 1] == "9"
    assert "--stop-on-loop" in preflight
    assert "--max-no-progress-turns" in preflight
    assert preflight[preflight.index("--max-no-progress-turns") + 1] == "12"

    assert live[live.index("--turns") + 1] == "888"
    assert live[live.index("--max-no-progress-turns") + 1] == "30"
    assert "--stop-on-loop" in live
    assert "--max-repeated-actions" in live
    assert live[live.index("--max-repeated-actions") + 1] == "4"


def test_bundle_ac_missing_command_flags_require_loop_guard_flags():
    namespace = _load_q_s_ac_namespace()

    missing = namespace["_bundle_q_missing_command_flags"](["--turns", "1000"])

    assert "--stop-on-loop" in missing
    assert "--max-repeated-actions" in missing
    assert "--max-no-progress-turns" in missing
    assert "--action-diversity-window" in missing
    assert "--min-action-diversity-rate" in missing
    assert "--player-agent-anti-loop-streak-threshold" in missing


def test_bundle_ac_profile_metadata_records_loop_guard_defaults():
    namespace = _load_q_s_ac_namespace()

    for profile_name in ("_BUNDLE_Q_PROFILE", "_BUNDLE_S_PROFILE"):
        defaults = namespace[profile_name]["defaults"]
        assert defaults["stop_on_loop"] is True
        assert defaults["max_repeated_actions"] == 4
        assert defaults["max_no_progress_turns"] == 12
        assert defaults["action_diversity_window"] == 8
        assert defaults["min_action_diversity_rate"] == 0.25
        assert defaults["player_agent_anti_loop_streak_threshold"] == 3
