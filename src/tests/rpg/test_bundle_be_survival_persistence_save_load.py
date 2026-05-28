from __future__ import annotations

import json

from app.rpg.session.response_builder import build_apply_turn_response
from app.rpg.session.service import create_or_normalize_session, export_session_as_package, import_session_from_package
from app.rpg.session.survival_persistence import (
    normalize_session_survival_for_persistence,
    survival_persistence_summary,
)
from app.rpg.survival import SURVIVAL_EVENT_LIMIT
from app.rpg.validation.integrity import validate_session_integrity, validate_survival_state


def _session_with_simulation(simulation_state):
    return {
        "manifest": {"id": "session:be", "title": "BE", "schema_version": 2},
        "installed_packs": [],
        "simulation_state": simulation_state,
        "runtime_state": {"tick": 5},
    }


def test_bundle_be_normalizes_canonical_survival_at_session_boundary() -> None:
    session = _session_with_simulation(
        {
            "survival": {
                "enabled": "true",
                "hunger": 150,
                "thirst": -10,
                "fatigue": "55",
                "last_food_turn": "7",
                "last_water_turn": "bad",
                "last_rest_turn": None,
                "events": [{"kind": f"event:{idx}"} for idx in range(SURVIVAL_EVENT_LIMIT + 4)],
                "llm_invented_extra": "drop_me",
            }
        }
    )

    normalized = create_or_normalize_session(session)
    survival = normalized["simulation_state"]["survival"]

    assert survival["enabled"] is True
    assert survival["hunger"] == 100
    assert survival["thirst"] == 0
    assert survival["fatigue"] == 55
    assert survival["last_food_turn"] == 7
    assert survival["last_water_turn"] is None
    assert "llm_invented_extra" not in survival
    assert len(survival["events"]) == SURVIVAL_EVENT_LIMIT
    assert survival["events"][0]["kind"] == "event:4"
    assert isinstance(normalized["runtime_state"], dict)
    json.dumps(normalized)


def test_bundle_be_legacy_needs_seed_canonical_survival_on_load() -> None:
    session = _session_with_simulation(
        {
            "needs": {"hunger": 42, "thirst": 76, "fatigue": 12},
            "player_state": {
                "needs": {"hunger": 99, "thirst": 99, "fatigue": 99},
            },
        }
    )

    normalized = normalize_session_survival_for_persistence(session)

    assert normalized["simulation_state"]["survival"] == {
        "enabled": True,
        "hunger": 42,
        "thirst": 76,
        "fatigue": 12,
        "last_food_turn": None,
        "last_water_turn": None,
        "last_rest_turn": None,
        "events": [],
    }
    summary = survival_persistence_summary(normalized["simulation_state"])
    assert summary["needs"] == {"hunger": 42, "thirst": 76, "fatigue": 12}


def test_bundle_be_package_export_import_preserves_bounded_survival_state() -> None:
    session = create_or_normalize_session(
        _session_with_simulation(
            {
                "survival": {
                    "hunger": 88,
                    "thirst": 77,
                    "fatigue": 66,
                    "events": [{"kind": f"e{idx}"} for idx in range(SURVIVAL_EVENT_LIMIT + 2)],
                    "bad_extra": "drop_me",
                },
                "memory_state": {},
                "presentation_state": {"visual_state": {}},
            }
        )
    )

    package = export_session_as_package(session)
    exported_survival = package["simulation_state"]["survival"]
    assert exported_survival["hunger"] == 88
    assert exported_survival["thirst"] == 77
    assert exported_survival["fatigue"] == 66
    assert len(exported_survival["events"]) == SURVIVAL_EVENT_LIMIT
    assert "bad_extra" not in exported_survival

    imported = import_session_from_package(package)
    assert imported["ok"] is True
    imported_survival = imported["session"]["simulation_state"]["survival"]
    assert imported_survival == exported_survival
    json.dumps(package)
    json.dumps(imported)


def test_bundle_be_integrity_reports_survival_errors_before_normalization() -> None:
    raw_session = _session_with_simulation(
        {
            "survival": {
                "hunger": 101,
                "thirst": "bad",
                "fatigue": 50,
                "events": [{"kind": f"e{idx}"} for idx in range(SURVIVAL_EVENT_LIMIT + 1)],
            },
            "memory_state": {},
            "presentation_state": {"visual_state": {}},
        }
    )

    integrity = validate_session_integrity(raw_session)
    codes = [item["code"] for item in integrity["errors"]]
    assert "survival_need_out_of_bounds" in codes
    assert "survival_need_invalid_type" in codes
    assert "survival_events_over_cap" in codes

    normalized = create_or_normalize_session(raw_session)
    assert validate_session_integrity(normalized)["ok"] is True
    assert validate_survival_state(normalized["simulation_state"])["ok"] is True


def test_bundle_be_build_apply_turn_response_after_normalized_load_projects_bd_context() -> None:
    session = create_or_normalize_session(
        _session_with_simulation(
            {
                "needs": {"hunger": 55, "thirst": 90, "fatigue": 10},
                "player_state": {
                    "inventory": {
                        "items": [
                            {
                                "item_id": "item:water",
                                "definition_id": "def:water",
                                "name": "Water",
                                "kind": "supply",
                                "quantity": 1,
                                "tags": ["water", "survival"],
                            }
                        ],
                        "equipment": {},
                    }
                },
            }
        )
    )
    authoritative_result = {
        "ok": True,
        "authoritative": {
            "resolved_result": {"ok": True},
            "deterministic_fallback_narration": "You check your supplies.",
        },
        "result": {"turn_id": "turn:be", "tick": 5},
        "turn_contract": {"ok": True, "resolved_result": {"ok": True}},
        "session": session,
    }

    response = build_apply_turn_response(authoritative_result)

    assert response["turn_contract"]["survival_pressure"] == {
        "hunger": "high",
        "thirst": "critical",
        "fatigue": "low",
    }
    assert response["result"]["autoplay_survival_pressure"]["should_respond"] is True
    assert response["result"]["suggested_actions"][0]["action"] == "drink water"
    json.dumps(response)
