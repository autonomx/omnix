from tests.rpg.autoplay_llm_campaign import _summarize_deferred_advisory_trace


def test_summarize_deferred_advisory_trace_counts_sources_and_candidates():
    transcript = [
        {
            "deferred_advisory_result": {
                "ok": True,
                "source": "provider_deferred_advisory",
                "worker_ms": 1000.0,
                "candidates": [
                    {"kind": "semantic_intent"},
                    {"kind": "memory"},
                ],
            }
        },
        {
            "deferred_advisory_result": {
                "ok": False,
                "source": "deferred_advisory_error",
                "worker_ms": 3000.0,
                "error": "boom",
                "candidates": [],
            }
        },
    ]

    summary = _summarize_deferred_advisory_trace(transcript)
    assert summary["turns"] == 2
    assert summary["ok_jobs"] == 1
    assert summary["failed_jobs"] == 1
    assert summary["sources"]["provider_deferred_advisory"] == 1
    assert summary["candidate_count"] == 2
    assert summary["candidate_kinds"]["memory"] == 1