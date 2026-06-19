"""Deterministic long-run item scenario coverage helpers."""
from __future__ import annotations

from typing import Any

ITEM_ENDURANCE_MILESTONES = (
    (5, "diagnostics"),
    (10, "pickup"),
    (15, "use_effect"),
    (20, "recipe_discovery"),
    (30, "crafting"),
    (40, "merchant"),
    (55, "modification"),
    (70, "combat"),
    (85, "maintenance"),
    (100, "report"),
)


def build_item_endurance_plan(*, total_turns: int = 100, source: str = "item_endurance_v1") -> dict[str, Any]:
    """Build a deterministic item-system coverage plan for long autoplay runs."""

    bounded_turns = max(1, int(total_turns))
    milestones = [_build_milestone(turn, kind, bounded_turns, source) for turn, kind in ITEM_ENDURANCE_MILESTONES if turn <= bounded_turns]
    if not milestones or milestones[-1]["turn"] != bounded_turns:
        milestones.append(_build_milestone(bounded_turns, "report", bounded_turns, source))
    return {
        "source": source,
        "total_turns": bounded_turns,
        "milestones": milestones,
        "coverage_targets": sorted({milestone["coverage_target"] for milestone in milestones}),
        "summary": {
            "milestone_count": len(milestones),
            "first_turn": milestones[0]["turn"],
            "final_turn": milestones[-1]["turn"],
        },
    }


def summarize_item_endurance_progress(plan: dict[str, Any], traces: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Summarize observed progress against a deterministic endurance plan."""

    observed_targets = _observed_targets(traces or [])
    milestones = [milestone for milestone in plan.get("milestones", []) if isinstance(milestone, dict)]
    expected_targets = [str(milestone.get("coverage_target")) for milestone in milestones]
    covered = [target for target in expected_targets if target in observed_targets]
    missing = [target for target in expected_targets if target not in observed_targets]
    score = len(set(covered)) / max(1, len(set(expected_targets)))
    return {
        "source": "item_endurance_progress_v1",
        "ok": not missing,
        "coverage_score": round(score, 4),
        "covered_targets": sorted(set(covered)),
        "missing_targets": sorted(set(missing)),
        "observed_targets": sorted(observed_targets),
        "expected_targets": sorted(set(expected_targets)),
    }


def _build_milestone(turn: int, kind: str, total_turns: int, source: str) -> dict[str, Any]:
    return {
        "turn": min(turn, total_turns),
        "coverage_target": kind,
        "source": source,
        "payload": _payload_for_kind(kind),
    }


def _payload_for_kind(kind: str) -> dict[str, Any]:
    if kind == "diagnostics":
        return {"action": "item_diagnostics", "record": True}
    if kind == "pickup":
        return {"action": "item_action", "item_action": {"action": "pickup"}}
    if kind == "use_effect":
        return {"action": "item_resolve", "command": "use a helpful item if available"}
    if kind == "recipe_discovery":
        return {"action": "item_action", "item_action": {"action": "recipe_discovery"}}
    if kind == "crafting":
        return {"action": "loadout_action", "loadout": {"action": "craft"}}
    if kind == "merchant":
        return {"action": "merchant_command", "command": "shop"}
    if kind == "modification":
        return {"action": "loadout_action", "loadout": {"action": "modify"}}
    if kind == "combat":
        return {"action": "item_action", "item_action": {"action": "combat"}}
    if kind == "maintenance":
        return {"action": "item_maintenance", "record_report": True}
    return {"action": "item_scenario", "run": False, "scenario_limit": 8}


def _observed_targets(traces: list[dict[str, Any]]) -> set[str]:
    targets: set[str] = set()
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        for key in ("coverage_target", "target", "kind", "action"):
            value = trace.get(key)
            if isinstance(value, str) and value:
                targets.add(value)
    return targets
