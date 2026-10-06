from __future__ import annotations


from app.apps.rpg.session.session_store import _normalize_session


def test_session_normalizer_preserves_manifest_counters_and_extensions() -> None:
    normalized = _normalize_session(
        {
            "manifest": {
                "id": "session:counters",
                "session_id": "session:counters",
                "schema_version": 5,
                "turn_count": 27,
                "checkpoint_sequence": 4,
                "custom_release_marker": "keep-me",
            },
            "simulation_state": {"tick": 27},
        }
    )

    manifest = normalized["manifest"]
    assert manifest["turn_count"] == 27
    assert manifest["checkpoint_sequence"] == 4
    assert manifest["custom_release_marker"] == "keep-me"
    assert normalized["simulation_state"]["tick"] == 27
