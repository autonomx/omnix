def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"digest source step {index % 7}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def _saved_artifacts():
    return {
        "transcript": {"rows": _turns(), "text": "digest source transcript"},
        "report": {"html": "<html><body>digest report</body></html>"},
        "checkpoint": {
            "final": {"digest": "digest:checkpoint:final"},
            "loaded": {"digest": "digest:checkpoint:final"},
            "expected": {"digest": "digest:checkpoint:final"},
        },
        "state": {
            "final": {"digest": "digest:state:final"},
            "loaded": {"digest": "digest:state:final"},
            "expected": {"digest": "digest:state:final"},
        },
        "artifact_source": "test_phase7_saved_autoplay_digest_source_integration",
    }


def test_ci_phase7_saved_autoplay_digest_source_capture_finds_nested_artifact_digests():
    from app.rpg.session import capture_saved_autoplay_digest_sources

    capture = capture_saved_autoplay_digest_sources(_saved_artifacts())
    digests = capture["digests"]
    metadata = capture["metadata"]

    assert capture["source"] == "deterministic_phase7_saved_autoplay_digest_source_gate"
    assert digests["final_checkpoint_digest"] == "digest:checkpoint:final"
    assert digests["loaded_checkpoint_digest"] == "digest:checkpoint:final"
    assert digests["expected_final_checkpoint_digest"] == "digest:checkpoint:final"
    assert digests["final_state_digest"] == "digest:state:final"
    assert digests["loaded_state_digest"] == "digest:state:final"
    assert digests["expected_final_state_digest"] == "digest:state:final"
    assert {row["kind"] for row in metadata} == set(digests.keys())
    assert {row["source"] for row in metadata} == {"deterministic_phase7_saved_autoplay_digest_source_gate"}


def test_ci_phase7_saved_autoplay_digest_source_threads_metadata_into_certification_payload():
    from app.rpg.session import build_saved_100_turn_certification_payload

    payload = build_saved_100_turn_certification_payload(_saved_artifacts())
    normalized = payload["normalized_artifact"]
    state_diff = payload["certification_result"]["state_diff"]

    assert payload["ok"] is True
    assert normalized["final_checkpoint_digest"] == "digest:checkpoint:final"
    assert normalized["final_state_digest"] == "digest:state:final"
    assert normalized["state_diff_source"] == "deterministic_phase7_saved_autoplay_digest_source_gate"
    assert normalized["digest_source_capture"]["source"] == "deterministic_phase7_saved_autoplay_digest_source_gate"
    assert len(normalized["digest_source_metadata"]) == 6
    assert {row["kind"] for row in state_diff["checks"]} == {
        "final_vs_loaded_checkpoint_digest",
        "final_vs_expected_checkpoint_digest",
        "final_vs_loaded_state_digest",
        "final_vs_expected_state_digest",
    }
    assert all(row["ok"] is True for row in state_diff["checks"])


def test_ci_phase7_saved_autoplay_digest_source_reports_checkpoint_and_state_mismatches_separately():
    from app.rpg.session import build_saved_100_turn_certification_payload

    saved = _saved_artifacts()
    saved["checkpoint"]["loaded"]["digest"] = "digest:checkpoint:loaded-drift"
    saved["checkpoint"]["expected"]["digest"] = "digest:checkpoint:expected-drift"
    saved["state"]["loaded"]["digest"] = "digest:state:loaded-drift"
    saved["state"]["expected"]["digest"] = "digest:state:expected-drift"
    payload = build_saved_100_turn_certification_payload(saved)
    blocker_kinds = {row["kind"] for row in payload["certification_result"]["blockers"]}
    blocker_sources = {row["source"] for row in payload["certification_result"]["blockers"]}

    assert payload["ok"] is False
    assert "final_vs_loaded_checkpoint_digest_mismatch" in blocker_kinds
    assert "final_vs_expected_checkpoint_digest_mismatch" in blocker_kinds
    assert "final_vs_loaded_state_digest_mismatch" in blocker_kinds
    assert "final_vs_expected_state_digest_mismatch" in blocker_kinds
    assert "deterministic_phase7_saved_autoplay_digest_source_gate" in blocker_sources


def test_ci_phase7_saved_autoplay_digest_source_ready_contract():
    from app.rpg.session import assert_phase7_saved_autoplay_digest_source_ready

    readiness = assert_phase7_saved_autoplay_digest_source_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_saved_autoplay_digest_source_gate_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase7_saved_autoplay_digest_source_gate"
    assert "Do not invent missing checkpoint or state digests." in readiness["contract"]["forbidden_claims"]
