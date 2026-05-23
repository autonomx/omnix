from __future__ import annotations

from app.rpg.session.survival_metrics import (
    build_survival_pressure_relief_summary,
    build_survival_runtime_probe_summary,
    survival_runtime_probe,
)


def _probe(applied=False, reason="thirst_below_critical_threshold"):
    return {
        "format_version": "n127101_runtime_attachment_probe_v1",
        "source": "n127101_critical_thirst_override_runtime_attachment_probe",
        "wrapper_called": True,
        "previous_apply_turn_called": True,
        "previous_apply_turn_returned": True,
        "promotion_called": True,
        "promotion_promoted": False,
        "promotion_reason": "no_backed_survival_suggestions",
        "persistence_called": True,
        "persistence_applied": True,
        "override_called": True,
        "override_applied": applied,
        "override_reason": reason,
        "override_action_kind": "drink_water" if applied else "",
        "turn_contract_attached": True,
        "runtime_state_attached": True,
        "override_needs_before": {"hunger": 20, "thirst": 100, "fatigue": 20},
        "override_needs_after": {"hunger": 20, "thirst": 70 if applied else 100, "fatigue": 20},
    }


def _row(turn_index, probe, nested="turn_contract"):
    row = {
        "turn_index": turn_index,
        "turn_contract": {
            "climate_survival": {
                "format_version": "n1231_climate_survival_state_v1",
                "runtime_enforced": True,
                "source": "deterministic_authoritative_turn_tick",
                "survival": {"hunger": 20, "thirst": 100, "fatigue": 20, "warnings": ["thirst_high"]},
            },
            "resource_changes": {"source": "n1231_climate_survival_tick", "hunger_delta": 1, "thirst_delta": 0, "fatigue_delta": 1},
        },
    }
    if nested == "top":
        row["survival_autoplay_runtime_probe"] = probe
    elif nested == "resource_changes":
        row["turn_contract"]["resource_changes"]["survival_autoplay_runtime_probe"] = probe
    else:
        row["turn_contract"]["survival_autoplay_runtime_probe"] = probe
    if probe.get("override_applied"):
        action = {"matched": True, "applied": True, "action_kind": "drink_water", "resource_changes": {"thirst_delta": -30, "inventory_consumed": {"consumed": True, "item_id": "autoplay_waterskin_1", "name": "Autoplay Waterskin"}}}
        row["turn_contract"]["survival_action"] = action
        row["turn_contract"]["resource_changes"]["survival_action"] = action
    return row


def test_n127101_extracts_runtime_probe_from_supported_locations() -> None:
    assert survival_runtime_probe(_row(1, _probe(), "top"))["wrapper_called"] is True
    assert survival_runtime_probe(_row(2, _probe(), "turn_contract"))["override_called"] is True
    assert survival_runtime_probe(_row(3, _probe(), "resource_changes"))["persistence_called"] is True


def test_n127101_builds_runtime_probe_summary_counts() -> None:
    summary = build_survival_runtime_probe_summary([
        _row(1, _probe(False, "thirst_below_critical_threshold")),
        _row(2, _probe(True, "critical_thirst_hard_override")),
    ])
    assert summary["probe_rows"] == 2
    assert summary["wrapper_called_rows"] == 2
    assert summary["override_called_rows"] == 2
    assert summary["override_applied_rows"] == 1
    assert summary["override_applied_ok"] is True
    assert summary["override_skip_reasons"]["critical_thirst_hard_override"] == 1


def test_n127101_pressure_summary_includes_runtime_probe_evidence() -> None:
    summary = build_survival_pressure_relief_summary([
        _row(1, _probe(False, "thirst_below_critical_threshold")),
        _row(2, _probe(True, "critical_thirst_hard_override")),
    ])
    assert summary["runtime_probe_summary"]["probe_rows"] == 2
    assert summary["runtime_probe_summary"]["override_applied_rows"] == 1
    coverage = summary["source_coverage_summary"]["coverage"]
    assert coverage["runtime_probe_rows"] == 2
    assert coverage["critical_thirst_override_called_rows"] == 2
    assert coverage["critical_thirst_override_applied_rows"] == 1
    assert summary["trend_rows"][1]["critical_thirst_override_applied"] is True
