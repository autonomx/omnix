from __future__ import annotations

from app.rpg.interactive_cli_campaign_map_state import OLD_MILL_LOCATION_ID, initial_campaign_map_state
from app.rpg.interactive_cli_map_proposal import (
    MAP_PROPOSAL_PROTOCOL_PATCH,
    apply_map_proposal_to_campaign_map,
    canonicalize_map_proposal,
)

_RIVER_COMMAND = "I keep following the old road east toward the river town."
_WATCHTOWER_COMMAND = "I push beyond the mill toward the broken watchtower."
_UNKNOWN_COMMAND = "I follow the deer trail beyond the known road."


def test_phase13_70_accepts_valid_llm_map_proposal() -> None:
    proposal = {
        "location": {
            "id": "location:riverside-ferry",
            "name": "riverside ferry",
            "kind": "settlement",
            "tags": ["river", "crossing", "service"],
        },
        "exit": {
            "from_location_id": OLD_MILL_LOCATION_ID,
            "direction": "east",
            "reverse_direction": "west",
        },
    }

    canonical = canonicalize_map_proposal(
        proposal,
        command=_RIVER_COMMAND,
        current_location_id=OLD_MILL_LOCATION_ID,
    )

    assert canonical["patch"] == MAP_PROPOSAL_PROTOCOL_PATCH
    assert canonical["status"] == "accepted"
    assert canonical["repairs"] == []
    assert canonical["location"]["id"] == "location:riverside-ferry"
    assert canonical["exit"]["from_location_id"] == OLD_MILL_LOCATION_ID
    assert canonical["exit"]["direction"] == "east"


def test_phase13_70_applies_valid_proposal_to_canonical_campaign_map() -> None:
    map_state = initial_campaign_map_state()
    proposal = {
        "location": {
            "id": "location:riverside-ferry",
            "name": "riverside ferry",
            "kind": "settlement",
            "tags": ["river", "crossing", "service"],
        },
        "exit": {
            "from_location_id": OLD_MILL_LOCATION_ID,
            "direction": "east",
            "reverse_direction": "west",
        },
    }

    updated_map, transition = apply_map_proposal_to_campaign_map(
        map_state,
        proposal,
        command=_RIVER_COMMAND,
        current_location_id=OLD_MILL_LOCATION_ID,
    )

    assert transition["to_location_id"] == "location:riverside-ferry"
    assert transition["proposal_status"] == "accepted"
    assert updated_map["locations"]["location:riverside-ferry"]["name"] == "riverside ferry"
    assert updated_map["locations"]["location:riverside-ferry"]["generated_from"] == "interactive_cli_map_proposal_v1"
    assert "location:riverside-ferry" in updated_map["discovered_location_ids"]
    assert updated_map["expansions"][-1]["policy"] == "canonicalize_llm_map_proposal"
    assert updated_map["expansions"][-1]["proposal_status"] == "accepted"
    assert updated_map["last_map_proposal"]["location"]["id"] == "location:riverside-ferry"


def test_phase13_70_repairs_malformed_but_useful_map_proposal() -> None:
    proposal = {
        "location": {
            "id": "WatchTower!!",
            "name": "Sunken Watchtower",
            "kind": "Ancient Ruin",
            "tags": ["Ruined Lookout", "Quest Hook", "Quest Hook", 17],
        },
        "exit": {
            "from_location_id": "location:wrong-place",
            "direction": "UP!",
            "reverse_direction": "UP!",
        },
    }

    canonical = canonicalize_map_proposal(
        proposal,
        command=_WATCHTOWER_COMMAND,
        current_location_id=OLD_MILL_LOCATION_ID,
    )

    assert canonical["status"] == "repaired"
    assert canonical["location"]["id"] == "location:sunken-watchtower"
    assert canonical["location"]["kind"] == "ancient_ruin"
    assert canonical["location"]["tags"][:3] == ["ruined_lookout", "quest_hook", "17"]
    assert canonical["exit"]["from_location_id"] == OLD_MILL_LOCATION_ID
    assert canonical["exit"]["direction"] == "outward"
    assert canonical["exit"]["reverse_direction"] == "back"
    assert "invalid_location_id_repaired" in canonical["repairs"]
    assert "exit_from_location_repaired" in canonical["repairs"]
    assert "invalid_direction_repaired" in canonical["repairs"]


def test_phase13_70_rejects_missing_proposal_and_uses_deterministic_fallback() -> None:
    canonical = canonicalize_map_proposal(
        None,
        command=_RIVER_COMMAND,
        current_location_id=OLD_MILL_LOCATION_ID,
    )

    assert canonical["status"] == "rejected"
    assert canonical["location"]["id"] == "location:river-town"
    assert canonical["location"]["name"] == "river town"
    assert canonical["location"]["kind"] == "settlement"
    assert canonical["exit"]["from_location_id"] == OLD_MILL_LOCATION_ID
    assert canonical["exit"]["direction"] == "east"
    assert "proposal_replaced_with_deterministic_fallback" in canonical["repairs"]


def test_phase13_70_applies_rejected_proposal_as_canonical_fallback_state() -> None:
    updated_map, transition = apply_map_proposal_to_campaign_map(
        initial_campaign_map_state(),
        None,
        command=_UNKNOWN_COMMAND,
        current_location_id=OLD_MILL_LOCATION_ID,
    )

    assert transition["map_expanded"] is True
    assert transition["proposal_status"] == "rejected"
    assert transition["to_location_id"] == "location:east-road"
    assert updated_map["locations"]["location:east-road"]["generated_from"] == "interactive_cli_map_proposal_v1"
    assert updated_map["expansions"][-1]["policy"] == "canonicalize_llm_map_proposal"
    assert updated_map["expansions"][-1]["proposal_status"] == "rejected"
    assert updated_map["expansions"][-1]["proposal_repairs"] == ["proposal_replaced_with_deterministic_fallback"]
    assert updated_map["last_map_proposal"]["status"] == "rejected"
