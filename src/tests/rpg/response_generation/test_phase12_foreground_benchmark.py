from __future__ import annotations

import runpy
from pathlib import Path


def _benchmark_namespace() -> dict:
    benchmark_path = (
        Path(__file__).resolve().parents[1]
        / "performance"
        / "foreground_turn_benchmark.py"
    )
    return runpy.run_path(str(benchmark_path))


def test_phase0_foreground_benchmark_is_provider_free_and_exactly_once(tmp_path: Path) -> None:
    namespace = _benchmark_namespace()
    report = namespace["run_foreground_turn_benchmark"](tmp_path)

    assert report["ok"] is True
    assert report["format_version"] == "rpg_foreground_turn_benchmark_v1"
    assert report["mode"] == "provider_free_deterministic"
    assert report["counts"] == {
        "apply_turn": 1,
        "provider_calls": 1,
        "session_loads": 1,
        "session_saves": 1,
        "interaction_seq": 1,
        "simulation_tick": 1,
    }
    assert report["job"]["record_count"] == 1
    assert report["job"]["statuses"] == ["completed"]
    assert report["job"]["transitions"] == {
        "create": 1,
        "mark_running": 1,
        "complete": 1,
        "fail": 0,
    }
    assert report["replay"]["idempotent_replay"] is True
    assert report["response"]["contract_version"] == "rpg_turn_response_v2"
    assert 0 < report["response"]["bytes"] <= 50_000
    assert "Bran:" in report["response"]["browser_visible_text"]
    assert report["ci_policy"]["live_provider_used"] is False
    assert report["ci_policy"]["latency_acceptance_enforced_here"] is False


def test_phase0_foreground_benchmark_documents_every_required_assertion(tmp_path: Path) -> None:
    namespace = _benchmark_namespace()
    report = namespace["run_foreground_turn_benchmark"](tmp_path)

    assert report["assertions"] == {
        "exactly_one_apply_turn": True,
        "exactly_one_provider_call": True,
        "exactly_one_session_load": True,
        "exactly_one_session_save": True,
        "one_completed_foreground_record": True,
        "idempotent_replay_reused_submission": True,
        "idempotent_replay_reused_interaction": True,
        "compact_response_within_limit": True,
        "browser_visible_bran_line": True,
    }
