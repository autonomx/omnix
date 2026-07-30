from __future__ import annotations

import pytest

from app.rpg.narrative_engine import CampaignBibleSnapshot, campaign_bible_evidence
from app.rpg.session.genesis import turn_grounding
from app.rpg.session.genesis.runtime_lore_materialization import (
    materialize_scene_lore,
    scene_lore_entity_is_rich,
)
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


def test_shallow_encountered_npc_is_upgraded_to_a_rich_character_dossier() -> None:
    class Gateway:
        calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            return """{
              "entities": [{
                "id": "npc:helix",
                "kind": "npc",
                "name": "Helix",
                "description": "Helix supervises salvage traffic through Tidebreak Docks.",
                "appearance": "A lean dock supervisor in an oil-dark coat with a brass ocular implant.",
                "personality": "Controlled, observant, and protective of the crews under his watch.",
                "backstory": "Helix survived the Seawall Collapse and rebuilt his standing by coordinating rescue crews.",
                "speech_style": "Short practical sentences, dock slang, and precise warnings.",
                "goals": ["Keep the tide gates operating", "Protect dock crews"],
                "motives": ["Prevent another infrastructure disaster"],
                "relationships": ["Trusted by maintenance crews"],
                "known_facts": ["Cargo manifests are being altered"],
                "current_situation": "Tracking irregular salvage shipments.",
                "dossier_status": "complete"
              }],
              "documents": [{
                "title": "Helix",
                "topic_id": "npcs",
                "full_text": "Helix supervises salvage traffic and watches for altered cargo manifests.",
                "entity_refs": ["npc:helix"]
              }],
              "facts": [],
              "relationships": []
            }"""

    session = _new_town_session()
    session["state"]["current_location"] = {}
    shallow = {
        "kind": "npc",
        "name": "Helix",
        "description": "Helix is a local NPC first encountered at Tidebreak Docks.",
        "visibility": "player_known",
    }
    gateway = Gateway()
    bible, report = materialize_scene_lore(
        {
            "entities": {"npc:helix": shallow},
            "documents": [{
                "document_id": "lore:npc:helix",
                "topic_id": "npcs",
                "title": "Helix",
                "full_text": shallow["description"],
                "entity_refs": ["npc:helix"],
                "visibility": "player_known",
            }],
        },
        session,
        {"scene": {"present_npc_ids": ["npc:helix"]}},
        campaign_id="campaign:new-town",
        llm_gateway=gateway,
    )

    helix = bible["entities"]["npc:helix"]
    assert gateway.calls == 1
    assert report["changed"] is True
    assert scene_lore_entity_is_rich(helix) is True
    assert helix["backstory"].startswith("Helix survived")
    assert helix["goals"] == ["Keep the tide gates operating", "Protect dock crews"]


def test_new_gameplay_item_is_materialized_into_the_items_topic_with_a_dossier() -> None:
    session = _new_town_session()
    session["state"]["current_location"] = {}
    bible, report = materialize_scene_lore(
        {},
        session,
        {
            "resolved_result": {
                "introduced_entities": [{
                    "item_id": "item:ghost-key",
                    "kind": "item",
                    "name": "Ghost Key",
                }],
            },
        },
        campaign_id="campaign:new-town",
        llm_gateway=False,
    )

    ghost_key = bible["entities"]["item:ghost-key"]
    assert report["created_entity_ids"] == ["item:ghost-key"]
    assert ghost_key["kind"] == "item"
    assert ghost_key["dossier"]["schema_version"] == "rpg_world_entity_dossier_v1"
    assert ghost_key["dossier"]["sections"]
    document = next(
        row
        for row in bible["documents"]
        if "item:ghost-key" in row.get("entity_refs", [])
    )
    assert document["topic_id"] == "equipment_vehicles"


def test_runtime_only_dialogue_still_includes_the_speakers_dossier(monkeypatch) -> None:
    projection = {
        "canon_revision": 4,
        "content_hash": "sha256:helix",
        "entities": {
            "npc:helix": {
                "kind": "npc",
                "name": "Helix",
                "description": "Helix supervises salvage traffic through Tidebreak Docks.",
                "appearance": "Oil-dark coat and brass ocular implant.",
                "personality": "Controlled and observant.",
                "backstory": "A survivor of the Seawall Collapse.",
                "speech_style": "Short practical sentences.",
                "goals": ["Keep the tide gates operating"],
                "motives": ["Protect the dock crews"],
                "visibility": "player_known",
            },
        },
        "documents": [{
            "document_id": "lore:npc:helix",
            "topic_id": "npcs",
            "title": "Helix",
            "full_text": "Helix supervises salvage traffic through Tidebreak Docks.",
            "entity_refs": ["npc:helix"],
            "visibility": "player_known",
        }],
        "discovery_state": {
            "pages": {"lore:npc:helix": "learned"},
            "entities": {"npc:helix": "learned"},
        },
    }
    session = {
        **_new_town_session(),
        "campaign_bible_projection": projection,
    }
    monkeypatch.setattr(
        turn_grounding,
        "sync_encountered_npc_lore",
        lambda *_args, **_kwargs: (session, {"mode": "already_synced"}),
    )
    monkeypatch.setattr(
        turn_grounding,
        "ensure_turn_scene_lore",
        lambda *_args, **_kwargs: (
            session,
            {
                "mode": "already_materialized",
                "persisted": True,
                "target_entity_ids": ["npc:helix"],
            },
        ),
    )
    monkeypatch.setattr(turn_grounding, "runtime_evidence", lambda _result: ())

    packet = turn_grounding.build_turn_grounding_packet(
        {
            "session": session,
            "resolved_result": {"response_mode": "dialogue"},
        },
        campaign_id="campaign:new-town",
        player_input="What are you doing here?",
        speaker_id="npc:helix",
        actor_ids=("npc:helix",),
        runtime_only=True,
    )

    assert packet.metadata["runtime_only"] is True
    assert packet.metadata["campaign_bible_evidence_count"] >= 2
    assert all("npc:helix" in record.entity_refs for record in packet.evidence)
    assert any("Seawall Collapse" in record.content for record in packet.evidence)


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
