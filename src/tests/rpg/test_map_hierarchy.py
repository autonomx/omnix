from __future__ import annotations

from app.rpg.map_actions import MapActionRequest, apply_map_action
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_hierarchy import hierarchy_breadcrumbs
from app.rpg.map_hierarchy_fixtures import FROSTED_FLAGON_INTERIOR_MAP_ID
from app.rpg.map_projection import initial_map_session_state, project_session_map_overlay
from app.rpg.map_repository import default_map_repository


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:test", "session_id": "session:test"},
        "state": {
            "session_id": "session:test",
            "current_turn": 1,
            "player": {"location_id": "rusty_flagon_tavern"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def test_hierarchy_breadcrumbs_are_root_to_leaf() -> None:
    repository = default_map_repository()

    assert hierarchy_breadcrumbs(FROSTED_FLAGON_INTERIOR_MAP_ID, repository) == (
        "region:northern_pass",
        FROST_HAVEN_MAP_ID,
        FROSTED_FLAGON_INTERIOR_MAP_ID,
    )


def test_enter_child_map_and_exit_to_parent_restore_overlay_state() -> None:
    repository = default_map_repository()
    session = _session()
    parent_overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)
    enter = MapActionRequest(
        action="enter",
        target_object_id="building:frost_haven_inn",
        definition_revision=parent_overlay.definition_revision,
        overlay_revision=parent_overlay.overlay_revision,
        client_action_id="action:enter-inn",
    )

    entered = apply_map_action(session, FROST_HAVEN_MAP_ID, enter, repository)

    assert entered["map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert entered["session"]["state"]["map_state"]["current_map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert entered["overlay"].availability == "ready"
    assert entered["overlay"].current_location_id == "rusty_flagon_tavern"
    assert "interior:flagon_counter" in entered["overlay"].visible_object_ids

    interior_overlay = entered["overlay"]
    exit_request = MapActionRequest(
        action="enter",
        target_object_id="interior:flagon_entry",
        definition_revision=interior_overlay.definition_revision,
        overlay_revision=interior_overlay.overlay_revision,
        client_action_id="action:exit-inn",
    )
    exited = apply_map_action(entered["session"], FROSTED_FLAGON_INTERIOR_MAP_ID, exit_request, repository)

    assert exited["map_id"] == FROST_HAVEN_MAP_ID
    assert exited["session"]["state"]["map_state"]["current_map_id"] == FROST_HAVEN_MAP_ID
    assert exited["overlay"].current_location_id == "rusty_flagon_tavern"
    assert "building:frost_haven_market" in exited["overlay"].visible_object_ids
    assert exited["session"]["state"]["map_state"]["map_history"][-2:] == [
        FROSTED_FLAGON_INTERIOR_MAP_ID,
        FROST_HAVEN_MAP_ID,
    ]
