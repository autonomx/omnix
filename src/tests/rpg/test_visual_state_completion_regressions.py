from __future__ import annotations

from app.rpg.presentation.visual_state import (
    append_scene_illustration,
    append_visual_asset,
    build_visual_asset_record,
    ensure_visual_state,
)
from app.rpg.visual.worker import _complete_character_portrait


def test_complete_character_portrait_persists_public_url_and_local_path():
    simulation_state = ensure_visual_state({
        "presentation_state": {
            "visual_state": {
                "character_visual_identities": {
                    "npc_guard_captain": {
                        "portrait_url": "",
                        "portrait_asset_id": "",
                        "status": "pending",
                        "version": 1,
                    }
                }
            }
        }
    })

    simulation_state = _complete_character_portrait(
        simulation_state,
        request={"target_id": "npc_guard_captain"},
        asset_id="character_portrait:npc_guard_captain:1:123",
        image_url="/generated-images/guard.png",
        local_path="resources/data/generated_images/guard.png",
        status="complete",
    )

    identity = simulation_state["presentation_state"]["visual_state"]["character_visual_identities"]["npc_guard_captain"]
    assert identity["portrait_url"] == "/generated-images/guard.png"
    assert identity["portrait_local_path"] == "resources/data/generated_images/guard.png"
    assert identity["portrait_asset_id"] == "character_portrait:npc_guard_captain:1:123"
    assert identity["status"] == "complete"


def test_append_scene_illustration_replaces_matching_event_id():
    simulation_state = ensure_visual_state({})

    simulation_state = append_scene_illustration(
        simulation_state,
        {
            "scene_id": "loc_tavern",
            "event_id": "scene:req1",
            "title": "The Rusty Flagon Tavern",
            "image_url": "/generated-images/old.png",
            "local_path": "resources/data/generated_images/old.png",
            "asset_id": "scene_illustration:loc_tavern:1:111",
            "status": "complete",
        },
    )
    simulation_state = append_scene_illustration(
        simulation_state,
        {
            "scene_id": "loc_tavern",
            "event_id": "scene:req1",
            "title": "The Rusty Flagon Tavern",
            "image_url": "/generated-images/new.png",
            "local_path": "resources/data/generated_images/new.png",
            "asset_id": "scene_illustration:loc_tavern:1:111",
            "status": "complete",
        },
    )

    illustrations = simulation_state["presentation_state"]["visual_state"]["scene_illustrations"]
    assert len(illustrations) == 1
    assert illustrations[0]["image_url"] == "/generated-images/new.png"
    assert illustrations[0]["local_path"] == "resources/data/generated_images/new.png"


def test_append_visual_asset_replaces_matching_asset_id():
    simulation_state = ensure_visual_state({})

    simulation_state = append_visual_asset(
        simulation_state,
        build_visual_asset_record(
            kind="scene_illustration",
            target_id="loc_tavern",
            version=1,
            seed=111,
            style="rpg-scene",
            model="default",
            prompt="old prompt",
            url="/generated-images/old.png",
            local_path="resources/data/generated_images/old.png",
            status="complete",
            created_from_request_id="scene:req1",
        ),
    )
    simulation_state = append_visual_asset(
        simulation_state,
        build_visual_asset_record(
            kind="scene_illustration",
            target_id="loc_tavern",
            version=1,
            seed=111,
            style="rpg-scene",
            model="default",
            prompt="new prompt",
            url="/generated-images/new.png",
            local_path="resources/data/generated_images/new.png",
            status="complete",
            created_from_request_id="scene:req1",
        ),
    )

    assets = simulation_state["presentation_state"]["visual_state"]["visual_assets"]
    assert len(assets) == 1
    assert assets[0]["url"] == "/generated-images/new.png"
    assert assets[0]["local_path"] == "resources/data/generated_images/new.png"
