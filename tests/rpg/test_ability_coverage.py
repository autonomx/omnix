from __future__ import annotations

from typing import Any

from app.rpg.session.ability_coverage import summarize_ability_coverage, write_ability_coverage_snapshot


def _coverage_state() -> dict[str, Any]:
    return {
        "ability_tree": {
            "abilities": [
                {
                    "ability_id": "recon_read_room",
                    "kind": "active",
                    "name": "Read the Room",
                    "capability": "recon",
                    "purpose": "information_gathering",
                    "dimensions": ["information", "narrative"],
                },
                {
                    "ability_id": "influence_broker_truce",
                    "kind": "active",
                    "name": "Broker Truce",
                    "capability": "influence",
                    "purpose": "world_influence",
                    "dimensions": ["relationships", "world"],
                },
                {
                    "ability_id": "keen_eye",
                    "kind": "passive",
                    "name": "Keen Eye",
                    "capability": "recon",
                    "purpose": "information_gathering",
                    "dimensions": ["information", "narrative"],
                },
                {
                    "ability_id": "former_detective",
                    "kind": "narrative_trait",
                    "name": "Former Detective",
                    "capability": "recon",
                    "purpose": "information_gathering",
                    "dimensions": ["information", "relationships", "narrative"],
                    "influence_tags": ["recognize_police_procedure"],
                },
            ]
        },
        "ability_state": {
            "unlocked": ["recon_read_room", "influence_broker_truce", "keen_eye", "former_detective"],
            "active_effects": [
                {
                    "ability_id": "recon_read_room",
                    "name": "Read the Room",
                    "dimensions": ["access"],
                    "purpose": "access_bypass",
                }
            ],
        },
        "mechanics": {
            "ability_effect_trace": [
                {
                    "ability_id": "recon_read_room",
                    "ability_name": "Read the Room",
                    "dimension": "information",
                    "op": "reveal_clue",
                    "applied": True,
                },
                {
                    "ability_id": "failed_power",
                    "ability_name": "Failed Power",
                    "dimension": "resources",
                    "op": "resource_delta",
                    "applied": False,
                },
            ],
            "world_effect_trace": [
                {
                    "ability_id": "influence_broker_truce",
                    "ability_name": "Broker Truce",
                    "dimension": "world",
                    "op": "add_world_event",
                    "applied": True,
                }
            ],
            "passive_hook_trace": [
                {
                    "ability_id": "keen_eye",
                    "ability_name": "Keen Eye",
                    "dimensions": ["relationships"],
                    "capability": "recon",
                }
            ],
        },
        "runtime": {
            "effects": [
                {
                    "source": "Warding Formula",
                    "dimension": "environment",
                    "check": "defense",
                    "amount": 2,
                }
            ],
            "passive_modifiers": [
                {
                    "ability_id": "keen_eye",
                    "source": "Keen Eye",
                    "dimensions": ["position"],
                    "capability": "recon",
                }
            ],
        },
        "timeline": [
            {
                "kind": "ability",
                "title": "Used Scavenge",
                "effects": [
                    {
                        "dimension": "resources",
                        "op": "resource_delta",
                        "applied": True,
                    }
                ],
            }
        ],
    }


def test_ability_coverage_summarizes_all_gameplay_dimensions() -> None:
    state = _coverage_state()

    report = summarize_ability_coverage(state)

    assert report.ok is False
    assert report.missing_dimensions == ["economy"]
    assert report.covered_dimensions == [
        "resources",
        "information",
        "relationships",
        "access",
        "environment",
        "position",
        "narrative",
        "world",
    ]
    assert report.dimension_counts["information"] >= 2
    assert report.dimension_counts["world"] == 1
    assert report.kind_counts["narrative_trait"] == 1
    assert report.source_counts["passive_hook_trace"] == 1
    assert report.source_counts["unlocked_narrative_trait"] == 1
    assert "failed_power" not in report.ability_counts


def test_ability_coverage_can_use_targeted_required_dimensions() -> None:
    state = _coverage_state()

    report = summarize_ability_coverage(state, required_dimensions=["resources", "information", "world"])

    assert report.ok is True
    assert report.missing_dimensions == []
    assert report.coverage_score == 1.0


def test_ability_coverage_marks_missing_dimensions() -> None:
    report = summarize_ability_coverage({}, required_dimensions=["resources", "information"])

    assert report.ok is False
    assert report.coverage_score == 0.0
    assert report.covered_dimensions == []
    assert report.missing_dimensions == ["resources", "information"]


def test_ability_coverage_ignores_unknown_dimensions_with_warning() -> None:
    state = {
        "mechanics": {
            "ability_effect_trace": [
                {
                    "ability_id": "strange_power",
                    "dimension": "not_a_dimension",
                    "op": "unknown",
                    "applied": True,
                }
            ]
        }
    }

    report = summarize_ability_coverage(state, required_dimensions=["resources"])

    assert report.ok is False
    assert report.dimension_counts == {}
    assert any("ignored unsupported dimension not_a_dimension" in warning for warning in report.warnings)


def test_ability_coverage_snapshot_is_written_to_mechanics() -> None:
    state = _coverage_state()

    report = write_ability_coverage_snapshot(state, required_dimensions=["resources", "information", "economy"])

    assert report.missing_dimensions == ["economy"]
    snapshot = state["mechanics"]["ability_coverage_snapshots"][0]
    assert snapshot["missing_dimensions"] == ["economy"]
    assert snapshot["covered_dimensions"] == ["resources", "information"]
    assert "observations" not in snapshot
    assert snapshot["created_at"].endswith("Z")
