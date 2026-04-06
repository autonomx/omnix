"""Phase A — Character UI builder unit tests.

Tests for canonical character UI state extraction:
- Empty state handling
- Personality profile integration
- Stable ordering
- Bounds on traits, actions, relationships
"""

from app.rpg.ui.character_builder import (
    build_character_inspector_entry,
    build_character_inspector_state,
    build_character_ui_entry,
    build_character_ui_state,
)


def test_build_character_ui_state_empty():
    """Empty simulation state returns empty character list."""
    result = build_character_ui_state({})
    assert result == {"characters": [], "count": 0}


def test_build_character_ui_state_missing_presentation():
    """Missing presentation_state returns empty character list."""
    result = build_character_ui_state({"some_other_key": "value"})
    assert result == {"characters": [], "count": 0}


def test_build_character_ui_entry_uses_personality_profile():
    """Character entry pulls personality data from simulation state."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:guard": {
                        "tone": "dry",
                        "archetype": "authority",
                        "style_tags": ["direct", "disciplined"],
                        "summary": "Veteran commander",
                    }
                }
            }
        }
    }

    entry = {
        "entity_id": "npc:guard",
        "speaker_name": "Captain Elira",
        "role": "guard_captain",
        "present": True,
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["id"] == "npc:guard"
    assert result["name"] == "Captain Elira"
    assert result["role"] == "guard_captain"
    assert result["kind"] == "character"
    assert result["personality"]["tone"] == "dry"
    assert result["personality"]["archetype"] == "authority"
    assert result["traits"] == ["direct", "disciplined"]


def test_build_character_ui_entry_fallback_id():
    """When no ID fields present, falls back to index-based ID."""
    simulation_state = {}
    entry = {"speaker_name": "Unknown"}

    result = build_character_ui_entry(simulation_state, entry, 3)
    assert result["id"] == "character:3"


def test_build_character_ui_entry_default_name():
    """When no name fields present, defaults to 'Unknown'."""
    simulation_state = {}
    entry = {"entity_id": "npc:1"}

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["name"] == "Unknown"


def test_build_character_ui_entry_default_role():
    """When no role fields present, defaults to 'character'."""
    simulation_state = {}
    entry = {"entity_id": "npc:1", "speaker_name": "Test"}

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["role"] == "character"


def test_build_character_ui_state_stable_ordering():
    """Character UI state sorts by speaker_order, then name, then id."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "b", "speaker_name": "Beta", "speaker_order": 2},
                {"entity_id": "a", "speaker_name": "Alpha", "speaker_order": 1},
            ]
        }
    }

    result = build_character_ui_state(simulation_state)
    assert [item["id"] for item in result["characters"]] == ["a", "b"]
    assert result["count"] == 2


def test_build_character_ui_state_missing_speaker_order():
    """Cards without speaker_order use fallback index."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "no_order", "speaker_name": "NoOrder"},
            ]
        }
    }

    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["meta"]["speaker_order"] == 0


def test_build_character_ui_relationships_bounded():
    """Relationship count is bounded to MAX_RELATIONSHIPS (8)."""
    simulation_state = {
        "social_state": {
            "relationships": {
                "npc:test": {
                    f"target:{i}": {"kind": "neutral", "score": i} for i in range(20)
                }
            }
        },
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:test", "speaker_name": "Test"}]
        },
    }

    result = build_character_ui_state(simulation_state)
    assert len(result["characters"][0]["relationships"]) == 8


def test_build_character_ui_recent_actions_bounded():
    """Recent actions count is bounded to MAX_RECENT_ACTIONS (5)."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "recent_actions": [f"action {i}" for i in range(20)],
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert len(result["recent_actions"]) == 5


def test_build_character_ui_traits_bounded():
    """Traits count is bounded to MAX_TRAITS (8)."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:test": {
                        "style_tags": [f"tag{i}" for i in range(20)]
                    }
                }
            }
        }
    }
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "traits": [f"trait{i}" for i in range(20)],
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert len(result["traits"]) <= 8


def test_build_character_ui_traits_deduplicated():
    """Duplicate traits are deduplicated (case-insensitive)."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "traits": ["Brave", "brave", "BRAVE", "Cowardly"],
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert len(result["traits"]) == 2
    assert "Brave" in result["traits"]
    assert "Cowardly" in result["traits"]


def test_build_character_ui_visual_identity():
    """Visual identity is extracted correctly."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "visual_identity": {
            "portrait_url": "https://example.com/portrait.png",
            "portrait_asset_id": "asset_123",
            "seed": 42,
            "style": "fantasy",
        },
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["visual_identity"]["portrait_url"] == "https://example.com/portrait.png"
    assert result["visual_identity"]["portrait_asset_id"] == "asset_123"
    assert result["visual_identity"]["seed"] == 42
    assert result["visual_identity"]["style"] == "fantasy"


def test_build_character_ui_current_intent_from_entry():
    """Current intent is taken from entry directly when present."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "current_intent": "investigate",
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["current_intent"] == "investigate"


def test_build_character_ui_current_intent_from_ai_state():
    """Current intent falls back to ai_state.npc_minds when not in entry."""
    simulation_state = {
        "ai_state": {
            "npc_minds": {
                "npc:test": {
                    "current_intent": "explore",
                }
            }
        }
    }
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["current_intent"] == "explore"


def test_build_character_ui_meta_present():
    """Meta present flag defaults to True when not specified."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["meta"]["present"] is True


def test_build_character_ui_meta_present_false():
    """Meta present flag is False when explicitly set."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test",
        "present": False,
    }

    result = build_character_ui_entry(simulation_state, entry, 0)
    assert result["meta"]["present"] is False


def test_build_character_ui_state_empty_speaker_cards():
    """Empty speaker_cards list returns empty result."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": []
        }
    }

    result = build_character_ui_state(simulation_state)
    assert result == {"characters": [], "count": 0}


def test_build_character_ui_skips_empty_entries():
    """Empty dict entries in speaker_cards are skipped."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [{}, {"entity_id": "valid", "speaker_name": "Valid"}, {}]
        }
    }

    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["id"] == "valid"


def test_build_character_ui_deterministic():
    """Multiple calls with same input produce same output."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "a", "speaker_name": "Alpha"},
                {"entity_id": "b", "speaker_name": "Beta"},
            ]
        }
    }

    one = build_character_ui_state(simulation_state)
    two = build_character_ui_state(simulation_state)
    assert one == two


# ---- Phase 11.2 — Inspector unit tests ----


def test_build_character_inspector_entry_includes_inventory_goals_beliefs_and_quests():
    """Inspector entry includes normalized inventory, goals, beliefs, and quests."""
    simulation_state = {
        "ai_state": {
            "npc_minds": {
                "npc:guard": {
                    "goal": "protect the gate",
                    "beliefs": {
                        "player": {"trust": -1, "dangerous": True},
                    },
                }
            }
        },
        "inventory_state": {
            "npc:guard": [
                {"id": "sword", "name": "Sword", "quantity": 1},
                {"id": "key", "name": "Gate Key", "quantity": 1},
            ]
        },
        "quest_state": {
            "quests": [
                {
                    "id": "quest:gate",
                    "title": "Hold the Gate",
                    "status": "active",
                    "participants": ["npc:guard"],
                }
            ]
        },
        "presentation_state": {
            "speaker_cards": [
                {
                    "entity_id": "npc:guard",
                    "speaker_name": "Captain Elira",
                    "role": "guard_captain",
                }
            ]
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert result["inspector"]["goals"] == ["protect the gate"]
    assert len(result["inspector"]["beliefs"]) == 1
    assert len(result["inspector"]["inventory"]) == 2
    assert len(result["inspector"]["active_quests"]) == 1


def test_build_character_inspector_state_empty():
    """Empty simulation state returns empty inspector characters list."""
    result = build_character_inspector_state({})
    assert result == {"characters": [], "count": 0}


def test_build_character_inspector_entry_relationship_summary():
    """Inspector relationship_summary aggregates scores correctly."""
    simulation_state = {
        "social_state": {
            "relationships": {
                "npc:a": {
                    "npc:b": {"kind": "friendly", "score": 1},
                    "npc:c": {"kind": "enemy", "score": -1},
                    "npc:d": {"kind": "neutral", "score": 0},
                }
            }
        },
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:a", "speaker_name": "A"}],
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    summary = result["inspector"]["relationship_summary"]
    assert summary["positive"] == 1
    assert summary["negative"] == 1
    assert summary["neutral"] == 1


def test_build_character_inspector_inventory_bounds():
    """Inventory items are bounded to _MAX_INVENTORY_ITEMS (12)."""
    items = [{"id": f"item{i}", "name": f"Item {i}", "quantity": 1} for i in range(20)]
    simulation_state = {
        "inventory_state": {"npc:test": items},
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:test", "speaker_name": "Test"}],
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert len(result["inspector"]["inventory"]) == 12


def test_build_character_inspector_goals_bounds():
    """Goals are bounded to _MAX_GOALS (5)."""
    goals = [f"goal {i}" for i in range(10)]
    simulation_state = {
        "ai_state": {
            "npc_minds": {"npc:test": {"goals": goals}},
        },
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:test", "speaker_name": "Test"}],
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert len(result["inspector"]["goals"]) == 5


def test_build_character_inspector_beliefs_bounds():
    """Beliefs are bounded to _MAX_BELIEFS (8)."""
    beliefs = {f"target{i}": {"status": "known"} for i in range(15)}
    simulation_state = {
        "ai_state": {
            "npc_minds": {"npc:test": {"beliefs": beliefs}},
        },
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:test", "speaker_name": "Test"}],
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert len(result["inspector"]["beliefs"]) == 8


def test_build_character_inspector_quests_bounds():
    """Active quests are bounded to _MAX_ACTIVE_QUESTS (8)."""
    quests = [
        {
            "id": f"quest:{i}",
            "title": f"Quest {i}",
            "status": "active",
            "participants": ["npc:test"],
        }
        for i in range(15)
    ]
    simulation_state = {
        "quest_state": {"quests": quests},
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:test", "speaker_name": "Test"}],
        },
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert len(result["inspector"]["active_quests"]) == 8


def test_build_character_inspector_entry_preserves_base_fields():
    """Inspector entry still has all base character_ui fields."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test NPC",
        "role": "ally",
        "present": True,
        "speaker_order": 2,
    }

    result = build_character_inspector_entry(simulation_state, entry, 0)

    # Check base fields exist
    assert result["id"] == "npc:test"
    assert result["name"] == "Test NPC"
    assert result["role"] == "ally"
    assert result["kind"] == "character"
    assert result["meta"]["speaker_order"] == 2

    # Check inspector field exists
    assert "inspector" in result
    assert "inventory" in result["inspector"]
    assert "goals" in result["inspector"]
    assert "beliefs" in result["inspector"]
    assert "active_quests" in result["inspector"]
    assert "relationship_summary" in result["inspector"]


def test_build_character_inspector_state_ordering():
    """Inspector state maintains same deterministic ordering as UI state."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "b", "speaker_name": "Beta", "speaker_order": 2},
                {"entity_id": "a", "speaker_name": "Alpha", "speaker_order": 1},
            ]
        }
    }

    result = build_character_inspector_state(simulation_state)
    assert [item["id"] for item in result["characters"]] == ["a", "b"]
    assert result["count"] == 2


def test_build_character_inspector_empty_inventory_and_quests():
    """Missing inventory_state and quest_state return empty lists."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [{"entity_id": "npc:x", "speaker_name": "X"}],
        }
    }

    entry = simulation_state["presentation_state"]["speaker_cards"][0]
    result = build_character_inspector_entry(simulation_state, entry, 0)

    assert result["inspector"]["inventory"] == []
    assert result["inspector"]["active_quests"] == []
    assert result["inspector"]["beliefs"] == []
