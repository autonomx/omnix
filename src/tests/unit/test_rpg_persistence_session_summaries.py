from __future__ import annotations

from app.persistence import rpg_compat


def _session(session_id: str, title: str) -> dict:
    return {
        "manifest": {
            "id": session_id,
            "session_id": session_id,
            "title": title,
            "status": "active",
        },
        "state": {"location": {"name": "Rusty Flagon Tavern"}},
    }


def test_postgres_session_summaries_use_authoritative_sessions_and_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        rpg_compat,
        "list_sessions_from_postgres",
        lambda: [_session("session:new", "New"), _session("session:old", "Old")],
    )

    summaries = rpg_compat.list_session_summaries_from_postgres(limit=1)

    assert len(summaries) == 1
    assert summaries[0]["manifest"]["session_id"] == "session:new"
    assert summaries[0]["manifest"]["title"] == "New"


def test_campaign_listing_replaces_placeholder_manifest_id_with_database_id() -> None:
    record = {
        "id": "rpg_20260715_210431_3190ddc1",
        "state": _session("session:unknown", "Recovered campaign"),
    }

    listed = rpg_compat._campaign_state_for_listing(record)

    assert listed["manifest"]["id"] == "rpg_20260715_210431_3190ddc1"
    assert listed["manifest"]["session_id"] == "rpg_20260715_210431_3190ddc1"
    assert listed["manifest"]["title"] == "Recovered campaign"
    assert record["state"]["manifest"]["session_id"] == "session:unknown"
