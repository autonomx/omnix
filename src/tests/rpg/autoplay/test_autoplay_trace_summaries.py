from tests.rpg.autoplay_llm_campaign import (
    _summarize_deferred_narration_trace,
    _summarize_player_agent_trace,
)


def test_summarize_player_agent_trace_counts_sources_and_fallbacks():
    transcript = [
        {
            "selected_player_action": {
                "source": "llm_player_agent",
                "reason": "valid action",
            },
            "performance": {"player_agent_ms": 1000.0},
        },
        {
            "selected_player_action": {
                "source": "fallback_scripted",
                "fallback_reason": "invalid_json",
                "error": "bad json",
            },
            "performance": {"player_agent_ms": 3000.0},
        },
    ]

    summary = _summarize_player_agent_trace(transcript)

    assert summary["turns"] == 2
    assert summary["llm_turns"] == 1
    assert summary["fallback_turns"] == 1
    assert summary["selected_source_counts"]["llm_player_agent"] == 1
    assert summary["selected_source_counts"]["fallback_scripted"] == 1
    assert summary["fallback_reason_counts"]["invalid_json"] == 1
    assert summary["errors"]["bad json"] == 1
    assert summary["avg_player_agent_ms"] == 2000.0


def test_summarize_deferred_narration_trace_counts_provider_and_sources():
    transcript = [
        {
            "turn_index": 1,
            "deferred_narration_result": {
                "ok": True,
                "worker_ms": 5000.0,
                "narration_payload": {
                    "source": "provider_runtime_narration",
                },
                "diagnostics": {
                    "provider_shape": {
                        "present": True,
                        "type": "LMStudioProvider",
                    },
                },
            },
        },
        {
            "turn_index": 2,
            "deferred_narration_result": {
                "ok": True,
                "worker_ms": 1000.0,
                "narration_payload": {
                    "source": "deterministic_runtime_narration_fallback",
                    "original_error": "provider_missing",
                },
                "diagnostics": {
                    "provider_shape": {
                        "present": False,
                    },
                    "payload_original_error": "provider_missing",
                },
            },
        },
    ]

    summary = _summarize_deferred_narration_trace(transcript)

    assert summary["turns"] == 2
    assert summary["ok_jobs"] == 2
    assert summary["sources"]["provider_runtime_narration"] == 1
    assert summary["sources"]["deterministic_runtime_narration_fallback"] == 1
    assert summary["provider_present"] == 1
    assert summary["provider_missing"] == 1
    assert summary["errors"]["provider_missing"] == 1
    assert summary["avg_worker_ms"] == 3000.0