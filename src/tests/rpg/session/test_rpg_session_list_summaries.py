from __future__ import annotations

import json
import os

from app.gateway.rpg_session_routes import _attach_environment_snapshot_to_session
from app.rpg.session import list_summaries
from app.rpg.session import service


def _write_session(path, session):
    path.write_text(
        json.dumps({"save_version": "1.0", "session": session}),
        encoding="utf-8",
    )


def test_list_session_summaries_omit_large_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr(list_summaries, "ensure_session_dir", lambda: tmp_path)
    _write_session(
        tmp_path / "session_large.json",
        {
            "manifest": {
                "id": "session:large",
                "session_id": "session:large",
                "title": "Large Session",
            },
            "state": {
                "world": {
                    "environment": {
                        "absolute_minutes": 480,
                        "climate_profile_id": "temperate_lowlands",
                        "active_events": [{"condition": "rain"}],
                    }
                },
                "scene": {
                    "environment_context": {
                        "exposure": "outdoor",
                        "shelter": "unsheltered",
                    }
                },
            },
            "simulation_state": {"huge": ["x"] * 1000},
            "runtime_state": {"huge": ["y"] * 1000},
        },
    )

    [summary] = list_summaries.list_session_summaries_from_disk()

    assert summary["manifest"]["id"] == "session:large"
    assert summary["simulation_state"] == {}
    assert summary["runtime_state"] == {}
    assert summary["state"]["world"]["environment"]["absolute_minutes"] == 480
    assert "huge" not in json.dumps(summary)


def test_list_session_summaries_limit_returns_newest_files_first(tmp_path, monkeypatch):
    monkeypatch.setattr(list_summaries, "ensure_session_dir", lambda: tmp_path)
    older = tmp_path / "older.json"
    newer = tmp_path / "newer.json"
    _write_session(older, {"manifest": {"id": "older", "session_id": "older"}})
    _write_session(newer, {"manifest": {"id": "newer", "session_id": "newer"}})
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    [summary] = list_summaries.list_session_summaries_from_disk(limit=1)

    assert summary["manifest"]["id"] == "newer"


def test_service_summary_list_does_not_full_normalize(monkeypatch):
    summary = {
        "manifest": {"id": "session:row", "session_id": "session:row"},
        "state": {"world": {"environment": {"absolute_minutes": 480}}},
        "simulation_state": {},
        "runtime_state": {},
    }

    def fail_full_normalize(_session):
        raise AssertionError("full normalization should not run for list rows")

    monkeypatch.setattr(service, "list_session_summaries_from_disk", lambda **_kwargs: [summary])
    monkeypatch.setattr(service, "create_or_normalize_session", fail_full_normalize)

    [row] = service.list_session_summaries()

    assert row["manifest"]["id"] == "session:row"
    assert row["_integrity"]["ok"] is True


def test_session_summary_preserves_environment_snapshot_fields():
    session = {
        "manifest": {"id": "session:env", "session_id": "session:env"},
        "state": {
            "world": {
                "environment": {
                    "absolute_minutes": 480,
                    "climate_profile_id": "temperate_lowlands",
                    "active_events": [{"condition": "rain"}],
                }
            },
            "scene": {
                "environment_context": {
                    "exposure": "outdoor",
                    "shelter": "unsheltered",
                }
            },
        },
    }

    row = _attach_environment_snapshot_to_session(
        list_summaries.session_list_summary(session)
    )

    snapshot = row["state"]["environment_snapshot"]
    assert snapshot["weather"]["condition"] == "rain"
    assert row["state"]["environment_narration_contract"]["mode"] == "read_only"


def test_published_opening_summary_keeps_its_canonical_location():
    session = {
        "manifest": {"id": "session:published", "session_id": "session:published"},
        "state": {
            "current_location_name": "Tidebreak Docks",
            "published_world": {"world_id": "world:vesper-9"},
            "environment_snapshot": {
                "schema_version": "rpg_published_opening_environment_v1",
                "context": {"location_label": "Tidebreak Docks"},
            },
            "world": {"environment": {"absolute_minutes": 480}},
            "scene": {
                "environment_context": {"location_label": "Rusty Flagon Tavern"}
            },
        },
    }

    row = _attach_environment_snapshot_to_session(
        list_summaries.session_list_summary(session)
    )

    assert row["state"]["current_location_name"] == "Tidebreak Docks"
    assert row["state"]["environment_snapshot"]["context"]["location_label"] == (
        "Tidebreak Docks"
    )
