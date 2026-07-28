from __future__ import annotations

import pytest

from app.rpg.narrative_engine import CampaignBibleSnapshot, campaign_bible_evidence
from app.rpg.session.genesis import turn_grounding
from app.rpg.session.genesis.runtime_lore_materialization import materialize_scene_lore
from app.rpg.session.genesis.runtime_lore_store import ensure_turn_scene_lore


def _new_town_session() -> dict:
    return {
        "manifest": {"id": "campaign:new-town", "session_id": "campaign:new-town"},
        "state": {
            "title": "The Road Beyond",
            "current_location": {
                "id": "location:grayhaven",
                "name": "Grayhaven",
            },
        },
        "runtime_state": {},
        "simulation_state": {},
    }


def test_new_town_materializes_consistent_local_canon_and_inhabitants() -> None:
    session = _new_town_session()
    result = {
        "scene": {
            "location_id": "location:grayhaven",
            "present_monsters": [
                {
                    "monster_id": "monster:marsh-stalker",
                    "name": "Marsh Stalker",
                }
            ],
        }
    }

    bible, report = materialize_scene_lore(
        {},
        session,
        result,
        campaign_id="campaign:new-town",
        llm_gateway=False,
    )

    assert report["changed"] is True
    assert "location:grayhaven" in bible["entities"]
    location = bible["entities"]["location:grayhaven"]
    assert location["kind"] == "location"
    assert len(location["inhabitants"]) == 2
    assert all(entity_id in bible["entities"] for entity_id in location["inhabitants"])
    assert "monster:marsh-stalker" in bible["entities"]
    titles = {row["title"] for row in bible["documents"]}
    assert "Grayhaven" in titles
    assert "History of Grayhaven" in titles
    assert "Marsh Stalker" in titles
    assert any(
        "location:grayhaven" in row.get("entity_refs", [])
        for row in bible["facts"]
    )
    assert all(
        row.get("authority") == "objective_canon"
        for row in bible["facts"]
    )

    reused, second = materialize_scene_lore(
        bible,
        session,
        result,
        campaign_id="campaign:new-town",
        llm_gateway=False,
    )
    assert second["changed"] is False
    assert reused["documents"] == bible["documents"]
    assert reused["entities"] == bible["entities"]


def test_portable_projection_is_authority_when_postgresql_is_unavailable(monkeypatch) -> None:
    session = _new_town_session()
    result = {"scene": {"location_id": "location:grayhaven"}}

    monkeypatch.setattr(
        "app.rpg.session.genesis.runtime_lore_store.default_database",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.runtime_lore_store._save_portable_projection",
        lambda value: value,
    )

    hydrated, report = ensure_turn_scene_lore(
        "campaign:new-town",
        session,
        result,
        llm_gateway=False,
    )

    assert report["mode"] == "portable_projection_authority"
    assert report["persisted"] is True
    assert report["postgresql_persisted"] is False
    projection = hydrated["campaign_bible_projection"]
    assert projection["content_hash"]
    assert "location:grayhaven" in projection["entities"]
    assert any(
        "location:grayhaven" in row.get("entity_refs", [])
        for row in projection["documents"]
    )
    snapshot = CampaignBibleSnapshot(
        campaign_id="campaign:new-town",
        revision=projection["canon_revision"],
        content_hash=projection["content_hash"],
        document=projection,
        provenance={"source": "portable_projection_authority"},
        consistency_report={},
        completeness={},
    )
    evidence = campaign_bible_evidence(snapshot)
    assert any(
        "location:grayhaven" in record.entity_refs
        for record in evidence
    )


def test_turn_grounding_fails_closed_when_materialized_canon_cannot_be_loaded(monkeypatch) -> None:
    monkeypatch.setattr(
        turn_grounding,
        "sync_encountered_npc_lore",
        lambda campaign_id, session, **kwargs: (dict(session), {"mode": "noop"}),
    )
    monkeypatch.setattr(
        turn_grounding,
        "ensure_turn_scene_lore",
        lambda campaign_id, session, result, **kwargs: (
            dict(session),
            {
                "mode": "portable_projection_authority",
                "persisted": True,
                "changed": True,
                "target_entity_ids": ["location:lost-town"],
                "created_entity_ids": ["location:lost-town"],
                "created_document_ids": ["lore:locations:lost-town"],
            },
        ),
    )
    monkeypatch.setattr(turn_grounding, "load_campaign_bible_snapshot", lambda *args, **kwargs: None)

    with pytest.raises(
        RuntimeError,
        match="turn_lore_source_of_truth_unavailable:location:lost-town",
    ):
        turn_grounding.build_turn_grounding_packet(
            {
                "ok": True,
                "scene": {"location_id": "location:lost-town"},
                "session": {"state": {}},
                "resolved_result": {"response_mode": "observation"},
            },
            campaign_id="campaign:lost-town",
            player_input="What is this place?",
        )
