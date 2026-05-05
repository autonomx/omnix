from tests.rpg.autoplay.deferred_narration_guard import (
    deferred_runtime_narration_context,
    suppress_provider_runtime_narration,
)
from tests.rpg.autoplay.parallel_pipeline import (
    AutoplayBackgroundPipeline,
    attach_background_results_to_transcript,
)


def test_deferred_narration_job_does_not_mutate_authoritative_snapshot():
    pipeline = AutoplayBackgroundPipeline(background_workers=1, provider_workers=1)
    state = {
        "location": {"name": "The Mill"},
        "inventory_state": {"currency": {"gold": 5}},
    }
    pipeline.submit_deferred_narration(
        provider=None,
        session_id="s",
        turn_index=1,
        player_action="I inspect the mill door.",
        simulation_state=state,
        turn_contract={"result": "The door is swollen shut."},
        prefer_provider=False,
    )
    results = pipeline.drain()
    pipeline.shutdown()

    assert state == {
        "location": {"name": "The Mill"},
        "inventory_state": {"currency": {"gold": 5}},
    }
    assert results[0]["ok"] is True
    assert results[0]["mutated_authoritative_snapshot"] is False
    assert results[0]["narration_status"] == "ready"


def test_attach_background_results_preserves_turn_order_and_updates_rows():
    transcript = [
        {"turn_index": 1, "narration": "pending", "turn_result": {}},
        {"turn_index": 2, "narration": "pending", "turn_result": {}},
    ]
    results = [
        {
            "ok": True,
            "kind": "deferred_narration",
            "turn_index": 2,
            "narration_status": "ready",
            "narration": "Second narration.",
            "narration_payload": {"narration": "Second narration."},
            "worker_ms": 10.0,
        },
        {
            "ok": True,
            "kind": "deferred_narration",
            "turn_index": 1,
            "narration_status": "ready",
            "narration": "First narration.",
            "narration_payload": {"narration": "First narration."},
            "worker_ms": 20.0,
        },
    ]

    summary = attach_background_results_to_transcript(transcript, results)

    assert [row["turn_index"] for row in transcript] == [1, 2]
    assert transcript[0]["narration"] == "First narration."
    assert transcript[1]["narration"] == "Second narration."
    assert summary["narration_jobs"] == 2


def test_deferred_runtime_narration_context_suppresses_provider_runtime_narration():
    assert suppress_provider_runtime_narration() is False
    with deferred_runtime_narration_context(True):
        assert suppress_provider_runtime_narration() is True
    assert suppress_provider_runtime_narration() is False