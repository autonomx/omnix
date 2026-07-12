from __future__ import annotations

import json

from app.rpg.session import durable_store
from app.rpg.session.session_store import _normalize_session


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


def test_legacy_transcript_survives_disk_migration_save_and_restart(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    raw = {
        "save_version": "1.0",
        "session": {
            "manifest": {
                "id": "session:legacy",
                "session_id": "session:legacy",
                "schema_version": 4,
                "turn_count": 6,
            },
            "simulation_state": {"tick": 6},
            "runtime_state": {
                "transcript": [
                    {
                        "role": "player",
                        "text": "I ask Bran whether the road is safe.",
                        "turn_id": "turn:6",
                        "tick": 6,
                    },
                    {
                        "role": "assistant",
                        "speaker_id": "npc:bran",
                        "speaker": "Bran",
                        "text": "The old road is quiet enough that I would travel carefully.",
                    },
                ]
            },
        },
    }
    path = tmp_path / "session_legacy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = durable_store.load_session_from_disk("session:legacy")
    assert loaded is not None
    assert loaded["manifest"]["turn_count"] == 6
    assert loaded["simulation_state"]["tick"] == 6
    events = loaded["runtime_state"]["interaction_timeline"]["events"]
    assert [event["interaction_id"] for event in events] == ["interaction:1"]
    assert events[0]["turn_id"] == "turn:6"

    durable_store.save_session_to_disk(loaded, compact=True)
    restarted = durable_store.load_session_from_disk("session:legacy")

    assert restarted is not None
    assert restarted["manifest"]["turn_count"] == 6
    assert restarted["simulation_state"]["tick"] == 6
    restarted_events = restarted["runtime_state"]["interaction_timeline"]["events"]
    assert restarted_events == events
    assert restarted["runtime_state"]["legacy_interaction_migration"]["status"] == "completed"
