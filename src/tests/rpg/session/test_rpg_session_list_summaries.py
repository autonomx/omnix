from __future__ import annotations

import json

from app.apps.rpg.api.feature_routes.rpg_session_routes import _attach_environment_snapshot_to_session
from app.apps.rpg.session import list_summaries


def _write_session(path, session):
    path.write_text(
        json.dumps({"save_version": "1.0", "session": session}),
        encoding="utf-8",
    )


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
