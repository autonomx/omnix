"""Phase 11.3 — World inspector builder unit tests.

Tests for canonical world/faction/location UI state extraction:
- Empty state handling
- Faction and_location normalization
- World thread handling
- Bounds on collections
"""

from app.rpg.ui.world_builder import (
    build_faction_inspector_state,
    build_location_inspector_state,
    build_world_inspector_state,
)


def test_build_world_inspector_state_empty():
    """Empty simulation state returns empty world inspector state."""
    result = build_world_inspector_state({})
    assert result["summary"] == {"current_location": "", "current_region": "", "threat_level": None}
    assert result["threads"] == []
    assert result["thread_count"] == 0
    assert result["factions"] == {"factions": [], "count": 0}
    assert result["locations"] == {"locations": [], "count": 0}


def test_build_faction_inspector_state_empty():
    """Empty simulation state returns empty faction state."""
    result = build_faction_inspector_state({})
    assert result == {"factions": [], "count": 0}


def test_build_location_inspector_state_empty():
    """Empty simulation state returns empty location state."""
    result = build_location_inspector_state({})
    assert result == {"locations": [], "count": 0}


def test_build_faction_inspector_state_basic():
    """Basic faction state extraction from simulation."""
    simulation_state = {
        "faction_state": {
            "factions": {
                "faction:guard": {
                    "name": "City Guard",
                    "members": ["npc:guard1", "npc:guard2"],
                    "relationships": {
                        "faction:thieves": {"kind": "hostile", "score": -1},
                    },
                }
            }
        }
    }
    result = build_faction_inspector_state(simulation_state)
    assert result["count"] == 1
    assert result["factions"][0]["id"] == "faction:guard"
    assert result["factions"][0]["name"] == "City Guard"
    assert len(result["factions"][0]["members"]) == 2


def test_build_location_inspector_state_basic():
    """Basic location state extraction from simulation."""
    simulation_state = {
        "world_state": {
            "locations": {
                "loc:market": {
                    "name": "Market Square",
                    "tags": ["busy", "trade"],
                    "actors": ["npc:merchant"],
                }
            }
        }
    }
    result = build_location_inspector_state(simulation_state)
    assert result["count"] == 1
    assert result["locations"][0]["id"] == "loc:market"
    assert result["locations"][0]["name"] == "Market Square"
    assert "busy" in result["locations"][0]["tags"]


def test_build_world_inspector_state_with_threads():
    """World inspector state extracts threads correctly."""
    simulation_state = {
        "world_state": {
            "threads": [
                {"id": "thread:1", "title": "Threat Rising", "status": "open", "pressure": 5},
            ],
            "current_location": "loc:town",
            "current_region": "region:north",
        }
    }
    result = build_world_inspector_state(simulation_state)
    assert result["thread_count"] == 1
    assert result["threads"][0]["id"] == "thread:1"
    assert result["summary"]["current_location"] == "loc:town"
    assert result["summary"]["current_region"] == "region:north"


def test_build_faction_inspector_state_bounds():
    """Faction count is bounded to _MAX_FACTIONS (12)."""
    factions = {
        f"faction:{i}": {"name": f"Faction {i}"}
        for i in range(20)
    }
    simulation_state = {"faction_state": {"factions": factions}}
    result = build_faction_inspector_state(simulation_state)
    assert result["count"] == 12


def test_build_location_inspector_state_bounds():
    """Location count is bounded to _MAX_LOCATIONS (16)."""
    locations = {
        f"loc:{i}": {"name": f"Location {i}"}
        for i in range(25)
    }
    simulation_state = {"world_state": {"locations": locations}}
    result = build_location_inspector_state(simulation_state)
    assert result["count"] == 16


def test_build_location_inspector_tag_bounds():
    """Location tags are bounded to _MAX_LOCATION_TAGS (8)."""
    simulation_state = {
        "world_state": {
            "locations": {
                "loc:1": {
                    "name": "Test Location",
                    "tags": [f"tag{i}" for i in range(20)],
                }
            }
        }
    }
    result = build_location_inspector_state(simulation_state)
    assert len(result["locations"][0]["tags"]) == 8


def test_build_location_inspector_actor_bounds():
    """Location actors are bounded to _MAX_LOCATION_ACTORS (8)."""
    simulation_state = {
        "world_state": {
            "locations": {
                "loc:1": {
                    "name": "Test Location",
                    "actors": [f"actor{i}" for i in range(20)],
                }
            }
        }
    }
    result = build_location_inspector_state(simulation_state)
    assert len(result["locations"][0]["actors"]) == 8


def test_build_faction_relationships_bounds():
    """Faction relationships are bounded to _MAX_FACTION_RELATIONSHIPS (8)."""
    relationships = {
        f"faction:{i}": {"kind": "neutral", "score": 0}
        for i in range(15)
    }
    simulation_state = {
        "faction_state": {
            "factions": {
                "faction:main": {
                    "name": "Main Faction",
                    "relationships": relationships,
                }
            }
        }
    }
    result = build_faction_inspector_state(simulation_state)
    assert len(result["factions"][0]["relationships"]) == 8


def test_build_faction_members_bounds():
    """Faction members are bounded to _MAX_FACT_MEMBERS (8)."""
    simulation_state = {
        "faction_state": {
            "factions": {
                "faction:1": {
                    "name": "Faction One",
                    "members": [f"npc:{i}" for i in range(20)],
                }
            }
        }
    }
    result = build_faction_inspector_state(simulation_state)
    assert len(result["factions"][0]["members"]) == 8


def test_build_world_threads_bounds():
    """World threads are bounded to _MAX_WORLD_THREADS (12)."""
    simulation_state = {
        "world_state": {
            "threads": [
                {"id": f"thread:{i}", "title": f"Thread {i}"}
                for i in range(20)
            ]
        }
    }
    result = build_world_inspector_state(simulation_state)
    assert result["thread_count"] == 12


def test_build_faction_inspector_deterministic():
    """Multiple calls with same input produce same output."""
    simulation_state = {
        "faction_state": {
            "factions": {
                "faction:b": {"name": "Beta"},
                "faction:a": {"name": "Alpha"},
            }
        }
    }
    one = build_faction_inspector_state(simulation_state)
    two = build_faction_inspector_state(simulation_state)
    assert one == two


def test_build_location_inspector_deterministic():
    """Multiple calls with same input produce same output."""
    simulation_state = {
        "world_state": {
            "locations": {
                "loc:b": {"name": "Beta"},
                "loc:a": {"name": "Alpha"},
            }
        }
    }
    one = build_location_inspector_state(simulation_state)
    two = build_location_inspector_state(simulation_state)
    assert one == two


def test_build_world_inspector_deterministic():
    """Multiple calls with same input produce same output."""
    simulation_state = {
        "world_state": {
            "threads": [{"id": "t1", "title": "Thread One"}],
        }
    }
    one = build_world_inspector_state(simulation_state)
    two = build_world_inspector_state(simulation_state)
    assert one == two