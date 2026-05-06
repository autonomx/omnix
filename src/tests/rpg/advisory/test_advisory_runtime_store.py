from app.rpg.advisory.candidates import normalize_advisory_candidates
from app.rpg.advisory.runtime_store import (
    compact_deferred_advisory_runtime_summary,
    ingest_deferred_advisory_candidates,
)


def test_ingest_deferred_advisory_candidates_dedupes_and_summarizes():
    runtime_state = {}
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I ask Bran.",
        turn_contract={"player_input": "I ask Bran."},
        payload={
            "future_hook_candidates": [
                {"summary": "Bran may answer later."},
            ]
        },
    )

    first = ingest_deferred_advisory_candidates(
        runtime_state=runtime_state,
        candidates=candidates,
        turn_index=1,
        source="provider_combined_background_llm",
    )
    second = ingest_deferred_advisory_candidates(
        runtime_state=runtime_state,
        candidates=candidates,
        turn_index=1,
        source="provider_combined_background_llm",
    )

    assert first["added"] == 1
    assert second["duplicates"] == 1
    assert runtime_state["deferred_advisory"]["summary"]["candidates"]["total"] == 1


def test_compact_deferred_advisory_runtime_summary_counts_pending():
    runtime_state = {}
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I inspect.",
        turn_contract={"player_input": "I inspect."},
        payload={"future_hook_candidates": [{"summary": "Someone may notice."}]},
    )
    ingest_deferred_advisory_candidates(
        runtime_state=runtime_state,
        candidates=candidates,
        turn_index=1,
        source="test",
    )

    summary = compact_deferred_advisory_runtime_summary(runtime_state)

    assert summary["pending_total"] == 1
    assert summary["candidate_total"] == 1