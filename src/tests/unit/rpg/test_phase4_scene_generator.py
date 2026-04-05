"""Unit tests for Phase 4 — Scene / Encounter Generator."""

import pytest

from app.rpg.creator.world_scene_generator import (
    SCENE_TYPE_CONFLICT,
    SCENE_TYPE_ENCOUNTER,
    SCENE_TYPE_INVESTIGATION,
    SCENE_TYPE_NEGOTIATION,
    SCENE_TYPE_POLITICAL,
    VALID_SCENE_TYPES,
    _safe_list,
    _safe_str,
    _build_scene_id,
    _resolve_mapper,
    generate_scenes_from_incidents,
    generate_scenes_from_simulation,
    get_scene_type_info,
)


class TestSafeHelpers:
    def test_safe_list_returns_list(self):
        assert _safe_list([1, 2]) == [1, 2]

    def test_safe_list_returns_empty_for_non_list(self):
        assert _safe_list(None) == []
        assert _safe_list("str") == []
        assert _safe_list(42) == []

    def test_safe_str_returns_string(self):
        assert _safe_str("hello") == "hello"
        assert _safe_str("hello", "default") == "hello"

    def test_safe_str_returns_default_for_none(self):
        assert _safe_str(None, "default") == "default"

    def test_safe_str_returns_empty_default(self):
        assert _safe_str(None) == ""

    def test_build_scene_id(self):
        assert _build_scene_id("thread_alpha", "crisis") == "scene_thread_alpha_crisis"


class TestResolveMapper:
    def test_exact_type_match_thread_crisis(self):
        mapper = _resolve_mapper("thread_crisis")
        assert mapper is not None

    def test_exact_type_match_location_flashpoint(self):
        mapper = _resolve_mapper("location_flashpoint")
        assert mapper is not None

    def test_exact_type_match_faction_instability(self):
        mapper = _resolve_mapper("faction_instability")
        assert mapper is not None

    def test_exact_type_match_thread_mystery(self):
        mapper = _resolve_mapper("thread_mystery")
        assert mapper is not None

    def test_exact_type_match_thread_diplomatic(self):
        mapper = _resolve_mapper("thread_diplomatic")
        assert mapper is not None

    def test_keyword_match_crisis(self):
        mapper = _resolve_mapper("some_crisis_event")
        assert mapper is not None

    def test_keyword_match_flashpoint(self):
        mapper = _resolve_mapper("flashpoint_event")
        assert mapper is not None

    def test_keyword_match_instability(self):
        mapper = _resolve_mapper("faction_instability_crisis")
        assert mapper is not None

    def test_keyword_match_mystery(self):
        mapper = _resolve_mapper("great_mystery")
        assert mapper is not None

    def test_keyword_match_negotiation(self):
        mapper = _resolve_mapper("urgent_negotiation")
        assert mapper is not None

    def test_keyword_match_diplomatic(self):
        mapper = _resolve_mapper("diplomatic_mission")
        assert mapper is not None

    def test_keyword_match_investigation(self):
        mapper = _resolve_mapper("needs_investigation")
        assert mapper is not None

    def test_unknown_type_returns_none(self):
        mapper = _resolve_mapper("unknown_type_xyz")
        assert mapper is None


class TestGenerateScenesFromIncidents:
    def test_empty_incidents(self):
        result = generate_scenes_from_incidents([])
        assert result == []

    def test_none_incidents(self):
        result = generate_scenes_from_incidents(None)
        assert result == []

    def test_thread_crisis_generates_conflict_scene(self):
        incidents = [
            {
                "id": "inc_1",
                "type": "thread_crisis",
                "source_id": "thread_alpha",
                "summary": "Tensions rising",
                "pressure": 5,
            }
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        scene = result[0]
        assert scene["type"] == SCENE_TYPE_CONFLICT
        assert "thread_alpha" in scene["scene_id"]
        assert scene["actors"] == ["thread_alpha"]

    def test_location_flashpoint_generates_encounter_scene(self):
        incidents = [
            {
                "id": "inc_1",
                "type": "location_flashpoint",
                "source_id": "loc_market",
                "summary": "Riot at the market",
                "heat": 3,
            }
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        scene = result[0]
        assert scene["type"] == SCENE_TYPE_ENCOUNTER
        assert "loc_market" in scene["scene_id"]

    def test_faction_instability_generates_political_scene(self):
        incidents = [
            {
                "id": "inc_1",
                "type": "faction_instability",
                "source_id": "faction_rebels",
                "summary": "Rebel faction splits",
                "pressure": 4,
            }
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        scene = result[0]
        assert scene["type"] == SCENE_TYPE_POLITICAL

    def test_thread_mystery_generates_investigation_scene(self):
        incidents = [
            {
                "id": "inc_1",
                "type": "thread_mystery",
                "source_id": "mystery_thread",
                "summary": "Strange lights in the sky",
            }
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        scene = result[0]
        assert scene["type"] == SCENE_TYPE_INVESTIGATION

    def test_thread_diplomatic_generates_negotiation_scene(self):
        incidents = [
            {
                "id": "inc_1",
                "type": "thread_diplomatic",
                "source_id": "peace_talks",
                "summary": "Peace negotiations stall",
            }
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        scene = result[0]
        assert scene["type"] == SCENE_TYPE_NEGOTIATION

    def test_multiple_incidents(self):
        incidents = [
            {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
            {"id": "i2", "type": "location_flashpoint", "source_id": "l1", "summary": "Flash"},
            {"id": "i3", "type": "faction_instability", "source_id": "f1", "summary": "Split"},
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 3

    def test_max_scenes_cutoff(self):
        incidents = [
            {
                "id": f"i{n}",
                "type": "thread_crisis",
                "source_id": f"t{n}",
                "summary": f"Crisis {n}",
            }
            for n in range(30)
        ]
        result = generate_scenes_from_incidents(incidents, max_scenes=20)
        assert len(result) == 20

    def test_unknown_incident_type_skipped(self):
        incidents = [
            {"id": "i1", "type": "unknown_xyz", "source_id": "t1", "summary": "Unknown"},
        ]
        result = generate_scenes_from_incidents(incidents)
        assert result == []

    def test_incident_without_source_id(self):
        incidents = [
            {"id": "i1", "type": "thread_crisis", "summary": "No source"},
        ]
        result = generate_scenes_from_incidents(incidents)
        assert len(result) == 1
        assert "unknown" in result[0]["scene_id"]

    def test_scene_has_source_incident_id(self):
        incidents = [
            {"id": "inc_abc", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
        ]
        result = generate_scenes_from_incidents(incidents)
        assert result[0]["source_incident_id"] == "inc_abc"

    def test_scene_has_severity_field(self):
        incidents = [
            {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis", "severity": "high"},
        ]
        result = generate_scenes_from_incidents(incidents)
        assert result[0]["severity"] == "high"


class TestGenerateScenesFromSimulation:
    def test_with_top_level_incidents(self):
        state = {
            "incidents": [
                {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
            ]
        }
        result = generate_scenes_from_simulation(state)
        assert len(result) == 1

    def test_with_nested_simulation_state_incidents(self):
        state = {
            "simulation_state": {
                "incidents": [
                    {"id": "i1", "type": "thread_crisis", "source_id": "t1", "summary": "Crisis"},
                ]
            }
        }
        result = generate_scenes_from_simulation(state)
        assert len(result) == 1

    def test_no_incidents_returns_empty(self):
        state = {"some_key": "some_value"}
        result = generate_scenes_from_simulation(state)
        assert result == []


class TestGetSceneTypeInfo:
    def test_conflict_type(self):
        info = get_scene_type_info(SCENE_TYPE_CONFLICT)
        assert info["label"] == "Conflict"
        assert info["icon"] == "\u2694\uFE0F"

    def test_encounter_type(self):
        info = get_scene_type_info(SCENE_TYPE_ENCOUNTER)
        assert info["label"] == "Encounter"

    def test_political_type(self):
        info = get_scene_type_info(SCENE_TYPE_POLITICAL)
        assert info["label"] == "Political"

    def test_investigation_type(self):
        info = get_scene_type_info(SCENE_TYPE_INVESTIGATION)
        assert info["label"] == "Investigation"

    def test_negotiation_type(self):
        info = get_scene_type_info(SCENE_TYPE_NEGOTIATION)
        assert info["label"] == "Negotiation"

    def test_unknown_type(self):
        info = get_scene_type_info("custom_type")
        assert info["label"] == "custom_type"
        assert "custom_type" in info["description"]


class TestValidSceneTypes:
    def test_contains_expected_types(self):
        assert SCENE_TYPE_CONFLICT in VALID_SCENE_TYPES
        assert SCENE_TYPE_ENCOUNTER in VALID_SCENE_TYPES
        assert SCENE_TYPE_POLITICAL in VALID_SCENE_TYPES
        assert SCENE_TYPE_INVESTIGATION in VALID_SCENE_TYPES
        assert SCENE_TYPE_NEGOTIATION in VALID_SCENE_TYPES

    def test_is_frozenset(self):
        assert isinstance(VALID_SCENE_TYPES, frozenset)