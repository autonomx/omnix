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


def test_web_ui_exposes_world_forge_depth_and_lore_browser() -> None:
    wizard = (
        REPO_ROOT / "apps/web/src/features/rpg/RpgCreateCampaignWizard.tsx"
    ).read_text(encoding="utf-8")
    lore = (
        REPO_ROOT / "apps/web/src/features/rpg/RpgLorePanel.tsx"
    ).read_text(encoding="utf-8")
    tabs = (
        REPO_ROOT / "apps/web/src/features/rpg/RpgNarrativeTabs.tsx"
    ).read_text(encoding="utf-8")
    routes = (
        REPO_ROOT / "src/app/gateway/rpg_campaign_lore_routes.py"
    ).read_text(encoding="utf-8")
    for depth in ("quick", "standard", "epic"):
        assert f"value: '{depth}'" in wizard
    assert "World Forge depth" in wizard
    assert "RpgLorePanel" in tabs
    assert "World Forge generation evidence" in lore
    assert "/campaign-genesis" in routes
    assert "/lore/document" in routes
