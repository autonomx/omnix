from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.session.genesis.campaign_lore_api import (
    LoreDocumentForbidden,
    campaign_genesis_progress_payload,
    campaign_lore_document_payload,
    campaign_lore_payload,
    transition_lore_discovery,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _session() -> dict:
    return {
        "state": {
            "campaign_bible": {
                "canon_revision": 3,
                "content_hash": "sha256:bible",
                "discovery_state": {
                    "pages": {
                        "lore:realm": "public_at_campaign_start",
                        "lore:secret": "hidden_from_player",
                        "lore:disputed": "disputed",
                    },
                    "entities": {},
                    "discoveries": [],
                },
            }
        },
        "runtime_state": {
            "campaign_bible_revision": 3,
            "campaign_bible_content_hash": "sha256:bible",
            "campaign_generation": {
                "status": "ready",
                "stage": "launch_ready",
                "launch_ready": True,
                "percent": 100,
                "world_forge_jobs": [
                    {"topic_id": "realm", "status": "completed"},
                    {"topic_id": "npcs", "status": "completed"},
                ],
            },
        },
        "setup_payload": {
            "world_forge": {
                "topic_graph": {"graph_version": "v1"},
                "generation_jobs": [],
            }
        },
        "campaign_bible_projection": {
            "entities": {
                "npc:bran": {
                    "kind": "npc",
                    "name": "Bran",
                    "appearance": "A broad-shouldered innkeeper.",
                    "personality": "Practical and watchful.",
                    "secrets": ["Private caravan knowledge"],
                    "visibility": "game_master_canon",
                },
                "location:rusty_flagon": {
                    "kind": "location",
                    "name": "Rusty Flagon Tavern",
                    "sensory_profile": "Rain taps against warm shutters.",
                    "visibility": "partially_known",
                },
                "faction:hidden": {
                    "kind": "faction",
                    "name": "The Hidden Hand",
                    "description": "A secret faction.",
                    "visibility": "game_master_canon",
                },
            },
            "documents": [
                {
                    "document_id": "lore:realm",
                    "topic_id": "realm",
                    "title": "Kavrix",
                    "full_text": "Kavrix is a fractured realm.",
                    "summary_500": "Kavrix is a fractured realm.",
                    "summary_120": "A fractured realm.",
                    "keywords": ["kavrix"],
                    "visibility": "public",
                    "canon_revision": 3,
                },
                {
                    "document_id": "lore:secret",
                    "topic_id": "npcs",
                    "title": "Vexira's Secret",
                    "full_text": "Private NPC secret.",
                    "visibility": "game_master_canon",
                    "canon_revision": 3,
                },
                {
                    "document_id": "lore:disputed",
                    "topic_id": "history",
                    "title": "The Broken Calendar",
                    "full_text": "Two kingdoms dispute the date.",
                    "summary_120": "A disputed date.",
                    "visibility": "disputed",
                    "canon_revision": 3,
                },
            ],
            "discovery_state": {
                "pages": {
                    "lore:realm": "public_at_campaign_start",
                    "lore:secret": "hidden_from_player",
                    "lore:disputed": "disputed",
                },
                "entities": {},
                "discoveries": [],
            },
        },
    }


def test_lore_api_exposes_only_player_safe_known_dossiers() -> None:
    session = _session()
    session["campaign_bible_projection"]["entities"]["npc:bran"].update(
        {
            "description": "Bran keeps the Rusty Flagon running through bad weather.",
            "backstory": "He inherited the inn after years guarding merchant caravans.",
            "speech_style": "Plainspoken, dry, and careful with promises.",
            "goals": ["Keep travelers safe"],
            "motives": ["Protect the inn and its regulars"],
            "provenance": {"source": "runtime_scene_materialization_v1"},
        }
    )
    session["campaign_bible_projection"]["entities"]["item:ghost-key"] = {
        "kind": "item",
        "name": "Ghost Key",
        "description": "A wafer-thin access key copied from a drowned courier.",
        "appearance": "Black ceramic with a pulsing blue edge.",
        "properties": ["Opens obsolete Kestrel cargo locks"],
        "visibility": "player_known",
        "provenance": {"source": "runtime_scene_materialization_v1"},
    }
    session["campaign_bible_projection"]["discovery_state"]["entities"] = {
        "npc:bran": "partially_known",
        "location:rusty_flagon": "partially_known",
        "faction:hidden": "hidden_from_player",
        "item:ghost-key": "learned",
    }
    payload = campaign_lore_payload(session)
    assert [row["name"] for row in payload["dossiers"]["characters"]] == ["Bran"]
    assert [row["name"] for row in payload["dossiers"]["locations"]] == [
        "Rusty Flagon Tavern"
    ]
    assert payload["dossiers"]["factions"] == []
    assert "secrets" not in payload["dossiers"]["characters"][0]
    bran_card = payload["dossier_cards"]["characters"][0]
    assert bran_card["id"] == "npc:bran"
    assert bran_card["metadata"]["lore_origin"] == "gameplay"
    assert bran_card["dossier"]["schema_version"] == "rpg_world_entity_dossier_v1"
    assert {section["title"] for section in bran_card["dossier"]["sections"]} >= {
        "Overview",
        "Backstory",
        "Goals and Motives",
        "Speech Style",
    }
    ghost_key = payload["topic_cards"]["equipment_vehicles"][0]
    assert ghost_key["id"] == "item:ghost-key"
    assert ghost_key["metadata"]["lore_origin"] == "gameplay"
    assert ghost_key["dossier"]["sections"]


def test_lore_api_never_exposes_private_or_game_master_pages() -> None:
    payload = campaign_lore_payload(_session())
    ids = {row["document_id"] for row in payload["documents"]}
    assert ids == {"lore:realm", "lore:disputed"}
    assert payload["hidden_count"] == 1
    with pytest.raises(LoreDocumentForbidden):
        campaign_lore_document_payload(_session(), "lore:secret")
    realm = campaign_lore_document_payload(_session(), "lore:realm")
    assert realm["document"]["full_text"] == "Kavrix is a fractured realm."


def test_generation_progress_and_discovery_transition_are_structured() -> None:
    session = _session()
    progress = campaign_genesis_progress_payload(session)
    assert progress["launch_ready"] is True
    assert progress["completed_jobs"] == 2
    assert progress["campaign_bible_revision"] == 3
    updated = transition_lore_discovery(
        session,
        document_id="lore:disputed",
        status="learned",
        source="turn:17",
    )
    discovery = updated["campaign_bible_projection"]["discovery_state"]
    assert discovery["pages"]["lore:disputed"] == "learned"
    assert discovery["discoveries"][-1]["source"] == "turn:17"
    with pytest.raises(LoreDocumentForbidden):
        transition_lore_discovery(
            session,
            document_id="lore:secret",
            status="learned",
        )


def test_web_ui_selects_published_worlds_and_keeps_lore_browser() -> None:
    wizard = (
        REPO_ROOT / "src/apps/web/src/features/rpg/RpgCreateCampaignWizard.tsx"
    ).read_text(encoding="utf-8")
    catalog = (
        REPO_ROOT / "src/apps/web/src/features/rpg/RpgWorldCampaignCatalog.tsx"
    ).read_text(encoding="utf-8")
    lore = (
        REPO_ROOT / "src/apps/web/src/features/rpg/RpgLorePanel.tsx"
    ).read_text(encoding="utf-8")
    tabs = (
        REPO_ROOT / "src/apps/web/src/features/rpg/RpgNarrativeTabs.tsx"
    ).read_text(encoding="utf-8")
    routes = (
        REPO_ROOT / "src/app/gateway/rpg_campaign_lore_routes.py"
    ).read_text(encoding="utf-8")
    assert 'aria-label="Available campaign worlds"' in catalog
    assert "Existing campaigns for" in catalog
    assert "New campaign in" in catalog
    assert 'aria-label="Selected campaign world"' in wizard
    assert 'aria-label="Published scenario"' in wizard
    assert "rpgWorldLibraryClient.launchScenario" in wizard
    assert "world_revision:" in wizard
    assert "world_release:" in wizard
    assert "World Forge depth" not in wizard
    assert "world_forge: {" not in wizard
    assert "RpgLorePanel" in tabs
    assert "World Forge generation evidence" in lore
    assert "/campaign-genesis" in routes
    assert "/lore/document" in routes
    assert "/lore/regenerate" in routes
    assert "/lore/materialize" in routes
    assert "Optional generation direction" in lore
    assert "Create rules & lore" in lore
