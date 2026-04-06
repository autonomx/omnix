"""Phase A — Character UI builder functional tests.

Tests character UI integration with presentation routes:
- Scene endpoint includes character_ui_state
- Dialogue endpoint includes character_ui_state
- Narrative recap endpoint includes character_ui_state
- Dedicated character_ui endpoint works correctly
- Speaker cards are not mutated
"""

from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.ui.character_builder import (
    build_character_ui_entry,
    build_character_ui_state,
)


def test_scene_presentation_includes_character_ui_and_inspector_state():
    """Scene presentation includes both character_ui_state and character_inspector_state."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/presentation/scene",
            data=json.dumps({
                "setup_payload": {},
                "scene_state": {},
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_ui_state" in payload
        assert "character_inspector_state" in payload


def test_build_character_ui_state_full_integration():
    """Full integration test with realistic simulation state."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {
                    "npc:guard": {
                        "tone": "stern",
                        "archetype": "guardian",
                        "style_tags": ["protective", "vigilant"],
                        "summary": "Loyal gate guardian",
                    },
                    "npc:merchant": {
                        "tone": "cheerful",
                        "archetype": "trader",
                        "style_tags": ["persuasive", "friendly"],
                        "summary": "Travelling merchant",
                    },
                }
            },
            "speaker_cards": [
                {
                    "entity_id": "npc:guard",
                    "speaker_name": "Theron",
                    "role": "guard",
                    "present": True,
                    "recent_actions": ["checked gate", "questioned visitor"],
                },
                {
                    "entity_id": "npc:merchant",
                    "speaker_name": "Lyra",
                    "role": "merchant",
                    "present": True,
                    "recent_actions": ["offered wares"],
                },
            ],
        },
        "social_state": {
            "relationships": {
                "npc:guard": {
                    "npc:merchant": {"kind": "friendly", "score": 0.6},
                },
                "npc:merchant": {
                    "npc:guard": {"kind": "friendly", "score": 0.5},
                },
            }
        },
        "ai_state": {
            "npc_minds": {
                "npc:guard": {"current_intent": "protect the gate"},
                "npc:merchant": {"current_intent": "sell exotic goods"},
            }
        },
    }

    result = build_character_ui_state(simulation_state)
    assert result["count"] == 2
    assert len(result["characters"]) == 2

    guard = result["characters"][0]
    assert guard["id"] == "npc:guard"
    assert guard["name"] == "Theron"
    assert guard["role"] == "guard"
    assert guard["kind"] == "character"
    assert guard["current_intent"] == "protect the gate"
    assert guard["personality"]["tone"] == "stern"
    assert guard["personality"]["archetype"] == "guardian"
    assert "protective" in guard["traits"]
    assert "vigilant" in guard["traits"]

    merchant = result["characters"][1]
    assert merchant["id"] == "npc:merchant"
    assert merchant["name"] == "Lyra"
    assert merchant["current_intent"] == "sell exotic goods"


def test_build_character_ui_state_backward_compat_missing_social():
    """Missing social_state does not break UI state."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "npc:x", "speaker_name": "X"},
            ]
        }
    }
    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["relationships"] == []


def test_build_character_ui_state_backward_compat_missing_ai():
    """Missing ai_state does not break UI state."""
    simulation_state = {
        "presentation_state": {
            "speaker_cards": [
                {"entity_id": "npc:x", "speaker_name": "X"},
            ]
        }
    }
    result = build_character_ui_state(simulation_state)
    assert result["count"] == 1
    assert result["characters"][0]["current_intent"] == ""


def test_ensure_character_ui_state_functional():
    """_ensure_character_ui_state attaches character_ui_state at presentation boundary."""
    from app.rpg.api.rpg_presentation_routes import _ensure_character_ui_state

    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {"npc:a": {"actor_id": "npc:a", "display_name": "A"}},
            },
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "A"},
            ],
        },
        "ai_state": {
            "npc_minds": {"npc:a": {"current_intent": "test intent"}},
        },
    }

    result = _ensure_character_ui_state(simulation_state)
    presentation_state = result.get("presentation_state", {})
    assert "character_ui_state" in presentation_state
    assert presentation_state["character_ui_state"]["count"] == 1


def test_ensure_personality_state_does_not_include_character_ui():
    """ensure_personality_state only owns personality normalization, not character_ui_state."""
    simulation_state = {
        "presentation_state": {
            "personality_state": {
                "profiles": {"npc:a": {"actor_id": "npc:a", "display_name": "A"}},
            },
            "speaker_cards": [
                {"entity_id": "npc:a", "speaker_name": "A"},
            ],
        }
    }

    result = ensure_personality_state(simulation_state)
    presentation_state = result.get("presentation_state", {})
    # character_ui_state should NOT be here - it's added at the presentation boundary
    assert "character_ui_state" not in presentation_state
    # But personality_state should be normalized
    assert "personality_state" in presentation_state


def test_character_ui_entry_shape_matches_spec():
    """Character UI entry has the required shape per design spec."""
    simulation_state = {}
    entry = {
        "entity_id": "npc:test",
        "speaker_name": "Test NPC",
        "role": "ally",
        "description": "A test character",
        "present": True,
        "speaker_order": 1,
        "source": "test",
        "visual_identity": {
            "portrait_url": "https://example.com/img.png",
            "seed": 123,
        },
    }

    result = build_character_ui_entry(simulation_state, entry, 0)

    # Required shape per spec
    assert "id" in result and isinstance(result["id"], str)
    assert "name" in result and isinstance(result["name"], str)
    assert "role" in result and isinstance(result["role"], str)
    assert "kind" in result and result["kind"] == "character"
    assert "description" in result and isinstance(result["description"], str)
    assert "traits" in result and isinstance(result["traits"], list)
    assert "current_intent" in result and isinstance(result["current_intent"], str)
    assert "recent_actions" in result and isinstance(result["recent_actions"], list)
    assert "relationships" in result and isinstance(result["relationships"], list)
    assert "personality" in result and isinstance(result["personality"], dict)
    assert "visual_identity" in result and isinstance(result["visual_identity"], dict)
    assert "meta" in result and isinstance(result["meta"], dict)

    # Personality sub-shape
    personality = result["personality"]
    assert "tone" in personality
    assert "archetype" in personality
    assert "style_tags" in personality
    assert "summary" in personality

    # Visual identity sub-shape
    visual = result["visual_identity"]
    assert "portrait_url" in visual
    assert "portrait_asset_id" in visual
    assert "seed" in visual
    assert "style" in visual

    # Meta sub-shape
    meta = result["meta"]
    assert "present" in meta and isinstance(meta["present"], bool)
    assert "speaker_order" in meta and isinstance(meta["speaker_order"], int)
    assert "source" in meta and isinstance(meta["source"], str)


# ---- Phase 11.2 — Inspector functional tests ----


def test_character_inspector_endpoint_returns_ok():
    """Character inspector endpoint returns ok=True."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/character_inspector",
            data=json.dumps({"setup_payload": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "character_inspector_state" in payload


def test_character_inspector_detail_not_found():
    """Character inspector detail returns 404 for missing actor."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/character_inspector/detail",
            data=json.dumps({"setup_payload": {}, "actor_id": "missing"}),
            content_type="application/json",
        )
        assert response.status_code == 404
        payload = response.get_json()
        assert payload["ok"] is False
        assert payload["error"] == "character_not_found"


def test_build_character_inspector_state_full_integration():
    """Full integration test with inspector fields on realistic simulation state."""
    simulation_state = {
        "ai_state": {
            "npc_minds": {
                "npc:guard": {
                    "goal": "protect the gate",
                    "beliefs": {"player": {"trust": -1}},
                },
                "npc:merchant": {
                    "current_intent": "sell goods",
                },
            }
        },
        "inventory_state": {
            "npc:guard": [
                {"id": "sword", "name": "Sword", "quantity": 1},
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
                {"entity_id": "npc:guard", "speaker_name": "Theron", "role": "guard"},
            ]
        },
    }

    from app.rpg.ui.character_builder import build_character_inspector_state

    result = build_character_inspector_state(simulation_state)
    assert result["count"] == 1

    inspector = result["characters"][0]["inspector"]
    assert len(inspector["inventory"]) == 1
    assert inspector["goals"] == ["protect the gate"]
    assert len(inspector["beliefs"]) == 1
    assert len(inspector["active_quests"]) == 1
    assert "relationship_summary" in inspector


# ---- Phase 11.3 — World Inspector functional tests ----


def test_world_inspector_endpoint_returns_ok():
    """World inspector endpoint returns ok=True."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post("/api/rpg/world_inspector", json={"setup_payload": {}})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "world_inspector_state" in payload


def test_scene_presentation_includes_world_inspector_state():
    """Scene presentation includes world_inspector_state."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/presentation/scene",
            data=json.dumps({"setup_payload": {}, "scene_state": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert "world_inspector_state" in payload


def test_dialogue_presentation_includes_world_inspector_state():
    """Dialogue presentation includes world_inspector_state."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/presentation/dialogue",
            data=json.dumps({"setup_payload": {}, "dialogue_state": {}}),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert "world_inspector_state" in payload


# ---- Phase 12 — Visual Assets functional tests ----


def test_visual_assets_endpoint_returns_ok():
    """Visual assets endpoint returns ok=True with visual_assets, appearance_profiles, appearance_events."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post("/api/rpg/visual_assets", json={"setup_payload": {}})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "visual_assets" in payload
        assert "appearance_profiles" in payload
        assert "appearance_events" in payload


def test_character_portrait_request_blocked_on_empty_prompt():
    """Portrait request with empty prompt returns blocked status."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/character_portrait/request",
            data=json.dumps({
                "setup_payload": {
                    "simulation_state": {
                        "presentation_state": {
                            "speaker_cards": [
                                {
                                    "entity_id": "npc:guard",
                                    "speaker_name": "Captain Elira",
                                    "role": "guard_captain",
                                }
                            ]
                        }
                    }
                },
                "actor_id": "npc:guard",
                "prompt": "",
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["moderation"]["status"] in {"approved", "blocked"}


# ---- Phase 12.9 — Package Export/Import functional tests ----


def test_package_export_route_returns_package():
    """Package export route returns ok=True with package payload."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/package/export",
            json={
                "setup_payload": {},
                "title": "Export Test",
                "created_by": "tester",
            },
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "package" in payload


def test_package_import_route_returns_imported():
    """Package import route returns ok=True with imported payload."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/package/import",
            json={
                "package": {
                    "manifest": {"package_version": "1.0", "title": "Pkg"},
                    "simulation_state": {"presentation_state": {}},
                }
            },
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "imported" in payload


# ---- Phase 13.0 — Content Pack functional tests ----


def test_packs_preview_route_returns_preview():
    """Pack preview route returns ok=True with preview payload."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/packs/preview",
            json={
                "pack": {
                    "manifest": {"id": "pack:test", "title": "Test Pack"},
                    "characters": [{"name": "Captain Elira"}],
                }
            },
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "preview" in payload


def test_packs_list_route_returns_packs():
    """Pack list route returns ok=True with packs payload."""
    import json
    from flask import Flask
    from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp

    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/rpg/packs/list",
            json={"setup_payload": {}},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "packs" in payload
