import json
from argparse import Namespace
from pathlib import Path

from tests.rpg.autoplay.manual_turn_driver import merge_autoplay_simulation_state
from tests.rpg.autoplay_llm_campaign import run_autoplay_campaign, _narration_source, _replace_blocking_narration_with_pending


def test_autoplay_runner_fallback_executes_short_campaign(tmp_path: Path, monkeypatch):
    state_holder = {"state": {}}

    def fake_prepare(*, session_id, simulation_state, reset_session_state=True, **kwargs):
        state_holder["state"] = dict(simulation_state)
        return {"session_id": session_id, "simulation_state": state_holder["state"]}

    def fake_load_state(session_id):
        return dict(state_holder["state"])

    def fake_turn(*, session_id, player_action, turn_index, **kwargs):
        state_holder["state"]["turns"] = int(state_holder["state"].get("turns") or 0) + 1
        return {
            "ok": True,
            "runtime_name": "manual_harness._run_one_manual_turn",
            "turn_runtime": {
                "name": "manual_harness._run_one_manual_turn",
                "kind": "real",
                "compatibility": False,
            },
            "runtime": {
                "name": "manual_harness._run_one_manual_turn",
                "kind": "real",
                "compatibility": False,
            },
            "raw_result_keys": ["ok", "result", "session", "turn_contract"],
            "simulation_state": dict(state_holder["state"]),
            "turn_contract": {"player_action": player_action},
            "narration": "You continue.",
        }

    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign.prepare_autoplay_manual_session", fake_prepare)
    monkeypatch.setattr("tests.rpg.autoplay.manual_turn_driver.load_autoplay_simulation_state", fake_load_state)
    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign._call_turn_runtime", fake_turn)
    monkeypatch.setattr(
        "tests.rpg.autoplay_llm_campaign.validate_save_load_checkpoint",
        lambda **kwargs: {
            "ok": True,
            "turn_index": kwargs["turn_index"],
            "checkpoint": {"path": str(tmp_path / "fake-checkpoint.json")},
            "before_digest": {},
            "loaded_digest": {},
            "reloaded_digest": {},
            "root_compare": {"ok": True},
        },
    )

    args = Namespace(
        turns=3,
        session_id="autoplay_test_session",
        scenario_seed="tavern_story_seed",
        random_seed=None,
        list_scenario_seeds=False,
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
        checkpoint_every=1,
        max_state_bytes=2_000_000,
        max_roots=80,
        max_state_list_length=500,
        max_state_dict_keys=500,
        allow_checkpoint_failures=False,
        allow_state_bound_warnings=False,
        min_meaningful_progress_rate=0.0,
        max_churn_only_rate=1.0,
        max_churn_only_streak=0,
        max_objective_target_no_progress_streak=0,
        fail_on_post_objective_weak_progress=False,
        autoplay_base_response="deterministic",
        base_response_max_tokens=220,
        fail_on_dialogue_coverage_gap=False,
        action_diversity_window=12,
        min_action_diversity_rate=0.0,
        min_category_diversity_rate=0.0,
        latency_profile="evaluation",
        narration_mode="blocking",
        checkpoint_mode="blocking",
        background_workers=2,
        provider_workers=1,
    )

    args = Namespace(
        turns=3,
        session_id="autoplay_test_session",
        scenario_seed="tavern_story_seed",
        random_seed=None,
        list_scenario_seeds=False,
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
        checkpoint_every=1,
        max_state_bytes=2_000_000,
        max_roots=80,
        max_state_list_length=500,
        max_state_dict_keys=500,
        allow_checkpoint_failures=False,
        allow_state_bound_warnings=False,
        min_meaningful_progress_rate=0.0,
        max_churn_only_rate=1.0,
        max_churn_only_streak=0,
        max_objective_target_no_progress_streak=0,
        fail_on_post_objective_weak_progress=False,
        autoplay_base_response="deterministic",
        base_response_max_tokens=220,
        fail_on_dialogue_coverage_gap=False,
        action_diversity_window=12,
        min_action_diversity_rate=0.0,
        min_category_diversity_rate=0.0,
        latency_profile="evaluation",
        narration_mode="blocking",
        checkpoint_mode="blocking",
        background_workers=2,
        provider_workers=1,
    )

    summary = run_autoplay_campaign(args)

    assert summary["turns_executed"] == 3
    assert summary["health"]["metrics"]["compatibility_turn_runtime_count"] == 0
    assert summary["health"]["metrics"]["real_turn_runtime_count"] == 3
    assert summary["artifact_paths"]["zip"]
    assert Path(summary["artifact_paths"]["zip"]).exists()


def test_runner_merge_preserves_authoritative_roots_when_reload_is_partial():
    authoritative = {
        "campaign_journal_state": {
            "entries": [{"entry_id": "journal:witness:found"}]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:pursue_bandit_trail", "status": "completed"}
                    ]
                }
            }
        },
    }
    partial_reload = {
        "memory_state": {},
        "presentation_state": {},
    }

    merged = merge_autoplay_simulation_state(
        before_state=authoritative,
        returned_state=partial_reload,
    )

    assert merged["campaign_journal_state"] == authoritative["campaign_journal_state"]
    assert merged["story_arc_milestone_state"] == authoritative["story_arc_milestone_state"]
    assert "memory_state" in merged


def test_repeated_completed_state_does_not_create_new_progress_after_merge():
    from tests.rpg.autoplay.progress import classify_progress_delta

    authoritative = {
        "campaign_journal_state": {
            "entries": [{"entry_id": "journal:witness:bandit_trail"}]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:pursue_bandit_trail", "status": "completed"}
                    ]
                }
            }
        },
    }
    partial_reload = {"memory_state": {}, "presentation_state": {}}
    before = merge_autoplay_simulation_state(
        before_state=authoritative,
        returned_state=partial_reload,
    )
    after = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=partial_reload,
    )

    delta = classify_progress_delta(before_state=before, after_state=after)

    assert "milestone_added" not in delta["categories"]
    assert "milestone_completed" not in delta["categories"]
    assert "objective_completed" not in delta["categories"]
    assert "journal_entry_added" not in delta["categories"]


def test_runner_owned_authoritative_state_survives_repeated_partial_reloads():
    from copy import deepcopy

    from tests.rpg.autoplay.progress import classify_progress_delta

    authoritative_state = {
        "campaign_journal_state": {
            "entries": [
                {"entry_id": "journal:witness:found"},
                {"entry_id": "journal:witness:bandit_trail"},
            ]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "completed"},
                        {"milestone_id": "milestone:pursue_bandit_trail", "status": "completed"},
                    ]
                }
            }
        },
    }
    partial_reload = {
        "campaign_journal_state": {"entries": []},
        "story_arc_milestone_state": {"arcs": {}},
        "memory_state": {},
    }

    before_turn = deepcopy(authoritative_state)
    authoritative_state = merge_autoplay_simulation_state(
        before_state=authoritative_state,
        returned_state=partial_reload,
    )
    after_turn = merge_autoplay_simulation_state(
        before_state=authoritative_state,
        returned_state=partial_reload,
    )

    delta = classify_progress_delta(before_state=before_turn, after_state=after_turn)

    assert after_turn["campaign_journal_state"]["entries"]
    assert after_turn["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    assert "milestone_added" not in delta["categories"]
    assert "milestone_completed" not in delta["categories"]
    assert "objective_added" not in delta["categories"]
    assert "objective_completed" not in delta["categories"]
    assert "journal_entry_added" not in delta["categories"]


def test_runner_baseline_must_not_be_loaded_from_partial_manual_session():
    from copy import deepcopy

    from tests.rpg.autoplay.progress import classify_progress_delta

    authoritative_state = {
        "campaign_journal_state": {
            "entries": [
                {"entry_id": "journal:one"},
                {"entry_id": "journal:two"},
            ]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "completed"}
                    ]
                }
            }
        },
    }
    partial_manual_session_state = {
        "campaign_journal_state": {"entries": []},
        "story_arc_milestone_state": {"arcs": {}},
        "memory_state": {},
    }

    # Correct runner behavior: do not use partial manual session as before_state.
    before_state = deepcopy(authoritative_state)

    # Manual turn may return partial state; merge it into authoritative state,
    # but the authoritative roots must remain.
    after_state = merge_autoplay_simulation_state(
        before_state=authoritative_state,
        returned_state=partial_manual_session_state,
    )

    delta = classify_progress_delta(before_state=before_state, after_state=after_state)

    assert after_state["campaign_journal_state"]["entries"]
    assert after_state["story_arc_milestone_state"]["arcs"]
    assert "milestone_added" not in delta["categories"]
    assert "milestone_completed" not in delta["categories"]
    assert "objective_added" not in delta["categories"]
    assert "objective_completed" not in delta["categories"]
    assert "journal_entry_added" not in delta["categories"]


def test_run_autoplay_campaign_does_not_load_manual_session_inside_turn_loop():
    import ast
    from pathlib import Path

    source = Path("src/tests/rpg/autoplay_llm_campaign.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_autoplay_campaign"
    )

    loop_nodes = [node for node in ast.walk(fn) if isinstance(node, ast.For)]
    assert loop_nodes, "expected run_autoplay_campaign turn loop"

    bad_calls = []
    for loop in loop_nodes:
        for node in ast.walk(loop):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "load_autoplay_simulation_state":
                    bad_calls.append((node.lineno, node.col_offset))

    assert bad_calls == []


def test_run_autoplay_campaign_uses_last_committed_state_baseline():
    import ast
    from pathlib import Path

    source = Path("src/tests/rpg/autoplay_llm_campaign.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_autoplay_campaign"
    )

    assigned_names = {
        target.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert "last_committed_state" in assigned_names

    source_segment = ast.get_source_segment(source, fn) or ""
    assert "before_state = deepcopy(expected_baseline_state)" in source_segment
    assert "last_committed_state = deepcopy(final_turn_state)" in source_segment


def test_commit_authoritative_state_preserves_next_turn_baseline(monkeypatch):
    from tests.rpg import autoplay_llm_campaign

    saved = {}

    def fake_prepare(*, session_id, simulation_state, reset_session_state=False, runtime_narration="blocking"):
        saved["session_id"] = session_id
        saved["simulation_state"] = simulation_state
        saved["reset_session_state"] = reset_session_state
        return {"session_id": session_id, "simulation_state": simulation_state}

    monkeypatch.setattr(
        autoplay_llm_campaign,
        "prepare_autoplay_manual_session",
        fake_prepare,
    )

    state = {
        "campaign_journal_state": {
            "entries": [{"entry_id": "journal:one"}]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "completed"}
                    ]
                }
            }
        },
    }

    committed = autoplay_llm_campaign._commit_authoritative_state(
        session_id="s",
        authoritative_state=state,
    )

    assert committed == state
    assert saved["simulation_state"] == state
    assert saved["reset_session_state"] is False


def test_last_committed_state_carry_forward_prevents_false_progress():
    from copy import deepcopy

    from tests.rpg.autoplay.progress import classify_progress_delta

    last_committed_state = {
        "campaign_journal_state": {
            "entries": [{"entry_id": "journal:one"}]
        },
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "completed"}
                    ]
                }
            }
        },
    }

    # Turn N+1 baseline must come from last_committed_state, not from partial
    # session reload.
    expected_baseline_state = deepcopy(last_committed_state)
    partial_manual_state = {
        "campaign_journal_state": {"entries": []},
        "story_arc_milestone_state": {"arcs": {}},
        "memory_state": {},
    }

    authoritative_state = merge_autoplay_simulation_state(
        before_state=deepcopy(last_committed_state),
        returned_state=partial_manual_state,
    )
    final_turn_state = deepcopy(authoritative_state)
    last_committed_state = deepcopy(final_turn_state)

    delta = classify_progress_delta(
        before_state=expected_baseline_state,
        after_state=last_committed_state,
    )

    assert last_committed_state["campaign_journal_state"]["entries"]
    assert last_committed_state["story_arc_milestone_state"]["arcs"]
    assert "journal_entry_added" not in delta["categories"]
    assert "milestone_added" not in delta["categories"]
    assert "milestone_completed" not in delta["categories"]
    assert "objective_completed" not in delta["categories"]


def test_post_objective_flag_does_not_fail_without_warnings(tmp_path: Path, monkeypatch):
    state_holder = {
        "state": {
            "story_arc_milestone_state": {
                "arcs": {
                    "arc:witness_search": {
                        "milestones": [
                            {"title": "Find the witness", "status": "active"}
                        ]
                    }
                }
            }
        }
    }

    def fake_prepare(*, session_id, simulation_state, reset_session_state=True, **kwargs):
        state_holder["state"] = dict(simulation_state)
        return {"session_id": session_id, "simulation_state": state_holder["state"]}

    def fake_load_state(session_id):
        return dict(state_holder["state"])

    def fake_turn(*, session_id, player_action, turn_index, **kwargs):
        state_holder["state"]["turns"] = int(state_holder["state"].get("turns") or 0) + 1
        return {
            "ok": True,
            "runtime_name": "manual_harness._run_one_manual_turn",
            "simulation_state": dict(state_holder["state"]),
            "turn_contract": {"player_action": player_action},
            "narration": "You continue the objective.",
        }

    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign.prepare_autoplay_manual_session", fake_prepare)
    monkeypatch.setattr("tests.rpg.autoplay.manual_turn_driver.load_autoplay_simulation_state", fake_load_state)
    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign._call_turn_runtime", fake_turn)
    monkeypatch.setattr(
        "tests.rpg.autoplay_llm_campaign.validate_save_load_checkpoint",
        lambda **kwargs: {
            "ok": True,
            "turn_index": kwargs["turn_index"],
            "checkpoint": {"path": str(tmp_path / "fake-checkpoint.json")},
            "before_digest": {},
            "loaded_digest": {},
            "reloaded_digest": {},
            "root_compare": {"ok": True},
        },
    )
    monkeypatch.setattr(
        "tests.rpg.autoplay_llm_campaign.post_objective_false_progress_warnings",
        lambda transcript: [],
    )

    args = Namespace(
        turns=1,
        session_id="autoplay_post_objective_flag_test",
        scenario_seed="tavern_story_seed",
        random_seed=None,
        list_scenario_seeds=False,
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
        checkpoint_every=1,
        max_state_bytes=2_000_000,
        max_roots=80,
        max_state_list_length=500,
        max_state_dict_keys=500,
        allow_checkpoint_failures=False,
        allow_state_bound_warnings=False,
        min_meaningful_progress_rate=0.0,
        max_churn_only_rate=1.0,
        max_churn_only_streak=0,
        max_objective_target_no_progress_streak=0,
        fail_on_post_objective_weak_progress=True,
        autoplay_base_response="deterministic",
        base_response_max_tokens=220,
        fail_on_dialogue_coverage_gap=False,
        action_diversity_window=12,
        min_action_diversity_rate=0.0,
        min_category_diversity_rate=0.0,
        latency_profile="evaluation",
        narration_mode="blocking",
        checkpoint_mode="blocking",
        background_workers=2,
        provider_workers=1,
    )

    summary = run_autoplay_campaign(args)

    assert summary["health"]["ok"] is True
    assert summary["health"]["progress_quality"]["ok"] is True


def test_deferred_narration_mode_does_not_leave_provider_source_in_blocking_turn(tmp_path: Path, monkeypatch):
    state_holder = {"state": {}}
    runtime_modes = []

    def fake_prepare(*, session_id, simulation_state, reset_session_state=True, runtime_narration="blocking", **kwargs):
        runtime_modes.append(runtime_narration)
        state_holder["state"] = dict(simulation_state)
        return {
            "session_id": session_id,
            "simulation_state": state_holder["state"],
            "runtime_state": {
                "autoplay_deferred_narration": runtime_narration == "deferred",
                "performance": {
                    "enable_live_narration_llm": runtime_narration != "deferred",
                },
            },
        }

    def fake_load_state(session_id):
        return dict(state_holder["state"])

    def fake_turn(*, session_id, player_action, turn_index, runtime_narration="blocking", **kwargs):
        runtime_modes.append(runtime_narration)
        state_holder["state"]["turns"] = int(state_holder["state"].get("turns") or 0) + 1
        source = (
            "deferred_runtime_narration_pending"
            if runtime_narration == "deferred"
            else "provider_runtime_narration"
        )
        return {
            "ok": True,
            "runtime_name": "manual_harness._run_one_manual_turn",
            "simulation_state": dict(state_holder["state"]),
            "turn_contract": {"player_action": player_action},
            "narration": "Narration is being prepared...",
            "narration_payload": {
                "format_version": "rpg_narration_v2",
                "source": source,
                "narration": "Narration is being prepared...",
                "action": "The action is resolved.",
                "npc": {"speaker": "", "line": ""},
                "reward": "",
                "followup_hooks": [],
            },
        }

    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign.prepare_autoplay_manual_session", fake_prepare)
    monkeypatch.setattr("tests.rpg.autoplay.manual_turn_driver.load_autoplay_simulation_state", fake_load_state)
    monkeypatch.setattr("tests.rpg.autoplay_llm_campaign._call_turn_runtime", fake_turn)
    monkeypatch.setattr(
        "tests.rpg.autoplay_llm_campaign.validate_save_load_checkpoint",
        lambda **kwargs: {"ok": True, "turn_index": kwargs["turn_index"]},
    )

    args = Namespace(
        turns=1,
        session_id="autoplay_deferred_regression_test",
        scenario_seed="tavern_story_seed",
        random_seed=None,
        list_scenario_seeds=False,
        player_agent="fallback",
        strategy="balanced_story_player",
        player_agent_max_tokens=200,
        suggested_action_limit=12,
        artifact_detail="full",
        latency_profile="playable",
        narration_mode="deferred",
        checkpoint_mode="background",
        background_workers=1,
        provider_workers=1,
        output_dir=str(tmp_path),
        base_url="http://127.0.0.1:5000",
        start_app_server=False,
        server_startup_timeout=1,
        max_repeated_actions=5,
        max_no_progress_turns=0,
        stop_on_loop=False,
        fail_on_runtime_error=True,
        fail_on_compatibility_turn_runtime=True,
        max_player_agent_fallback_rate=1.0,
        fail_on_regression_warnings=True,
        debug_provider_shape=False,
        debug_turn_runtime_shape=False,
        checkpoint_every=0,
        max_state_bytes=2_000_000,
        max_roots=80,
        max_state_list_length=500,
        max_state_dict_keys=500,
        allow_checkpoint_failures=False,
        allow_state_bound_warnings=False,
        min_meaningful_progress_rate=0.0,
        max_churn_only_rate=1.0,
        max_churn_only_streak=0,
        max_objective_target_no_progress_streak=0,
        fail_on_post_objective_weak_progress=False,
        autoplay_base_response="deterministic",
        base_response_max_tokens=220,
        fail_on_dialogue_coverage_gap=False,
        action_diversity_window=12,
        min_action_diversity_rate=0.0,
        min_category_diversity_rate=0.0,
    )

    summary = run_autoplay_campaign(args)
    transcript = json.loads((tmp_path / "autoplay-transcript.json").read_text(encoding="utf-8"))
    source = transcript[0]["turn_result"]["narration_payload"]["source"]

    assert summary["ok"] is True
    assert "deferred" in runtime_modes
    assert source != "provider_runtime_narration"


def test_narration_source_detects_nested_turn_result_payload():
    row = {
        "turn_result": {
            "narration_payload": {
                "source": "provider_runtime_narration",
                "narration": "Provider narration.",
            }
        }
    }

    assert _narration_source(row) == "provider_runtime_narration"


def test_replace_blocking_narration_with_pending_updates_nested_payload():
    row = {
        "turn_result": {
            "narration_payload": {
                "source": "provider_runtime_narration",
                "narration": "Provider narration.",
            }
        }
    }

    _replace_blocking_narration_with_pending(row)

    assert row["narration_payload"]["source"] == "deferred_runtime_narration_pending"
    assert row["turn_result"]["narration_payload"]["source"] == "deferred_runtime_narration_pending"