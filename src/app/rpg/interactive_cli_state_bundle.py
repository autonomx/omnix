"""Aggregate interactive CLI state layers into one carry-forward bundle.

The bundle is intentionally deterministic and presentation/runtime-safe.  It does
not mutate simulation state; it collects the short-session state helpers that are
already attached to interactive feature-matrix turns so save/load and replay work
can reason about one coherent payload in later phases.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.interactive_cli_commerce_state import extract_commerce_state
from app.rpg.interactive_cli_equipment_state import extract_equipment_state
from app.rpg.interactive_cli_memory_state import extract_short_session_memory_state
from app.rpg.interactive_cli_travel_state import initial_travel_state

INTERACTIVE_CLI_STATE_BUNDLE_VERSION = "interactive_cli_state_bundle_v1"
INTERACTIVE_CLI_STATE_BUNDLE_PATCH = "phase_13_65_interactive_state_bundle_v1"
INTERACTIVE_CLI_STATE_BUNDLE_SOURCE = "interactive_cli_state_bundle"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _extract_travel_state(turn: Mapping[str, Any] | None = None) -> dict[str, Any]:
    turn_dict = _safe_dict(turn)
    raw_result = _safe_dict(turn_dict.get("raw_result") or turn_dict.get("result"))
    for candidate in (
        turn_dict.get("interactive_cli_travel_state"),
        raw_result.get("interactive_cli_travel_state"),
        turn_dict.get("travel_state"),
        raw_result.get("travel_state"),
    ):
        if isinstance(candidate, dict):
            return deepcopy(candidate)
    return initial_travel_state()


def build_interactive_cli_state_bundle(turn: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a normalized bundle from any state already present on a turn."""

    turn_dict = _safe_dict(turn)
    travel_state = _extract_travel_state(turn_dict)
    campaign_map_state = deepcopy(_safe_dict(travel_state.get("campaign_map_state")))
    equipment_state = extract_equipment_state(turn_dict)
    memory_state = extract_short_session_memory_state(turn_dict)
    commerce_state = extract_commerce_state(turn_dict)
    return {
        "version": INTERACTIVE_CLI_STATE_BUNDLE_VERSION,
        "patch": INTERACTIVE_CLI_STATE_BUNDLE_PATCH,
        "source": INTERACTIVE_CLI_STATE_BUNDLE_SOURCE,
        "turn_index": int(turn_dict.get("turn_index") or 0),
        "player_input": _safe_str(turn_dict.get("player_input") or turn_dict.get("player_action")),
        "states": {
            "equipment": equipment_state,
            "memory": memory_state,
            "travel": travel_state,
            "campaign_map": campaign_map_state,
            "commerce": commerce_state,
        },
        "state_versions": {
            "equipment": _safe_str(equipment_state.get("version")),
            "memory": _safe_str(memory_state.get("version")),
            "travel": _safe_str(travel_state.get("source")),
            "campaign_map": _safe_str(campaign_map_state.get("version")),
            "commerce": _safe_str(commerce_state.get("version")),
        },
    }


def attach_interactive_cli_state_bundle_to_turn(turn: Mapping[str, Any]) -> dict[str, Any]:
    """Return a turn copy with the aggregate state bundle attached."""

    out = deepcopy(_safe_dict(turn))
    bundle = build_interactive_cli_state_bundle(out)
    out["interactive_cli_state_bundle"] = bundle
    out["interactive_cli_state_bundle_patch"] = INTERACTIVE_CLI_STATE_BUNDLE_PATCH
    raw_result = deepcopy(_safe_dict(out.get("raw_result") or out.get("result")))
    raw_result["interactive_cli_state_bundle"] = bundle
    raw_result["interactive_cli_state_bundle_patch"] = INTERACTIVE_CLI_STATE_BUNDLE_PATCH
    out["raw_result"] = raw_result
    out["result"] = raw_result
    return out


def apply_interactive_cli_state_bundle_to_matrix_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Attach state bundles to every turn in a feature matrix result."""

    result_dict = _safe_dict(result)
    changed = 0
    scenarios: list[dict[str, Any]] = []
    for item in _safe_list(result_dict.get("results")):
        scenario = item.get("scenario")
        scenario_id = _safe_str(getattr(scenario, "scenario_id", "") or _safe_dict(scenario).get("scenario_id"))
        scenario_result = _safe_dict(item.get("result"))
        turns = []
        scenario_changed = 0
        for turn in _safe_list(scenario_result.get("turns")):
            turn_dict = _safe_dict(turn)
            bundled = attach_interactive_cli_state_bundle_to_turn(turn_dict)
            turns.append(bundled)
            scenario_changed += 1
        if scenario_result.get("turns") is not None:
            scenario_result["turns"] = turns
            item["result"] = scenario_result
        changed += scenario_changed
        scenarios.append({"scenario_id": scenario_id, "changed_turns": scenario_changed})
    summary = result_dict.get("summary")
    if isinstance(summary, dict):
        summary["interactive_cli_state_bundle"] = {
            "ok": True,
            "source": INTERACTIVE_CLI_STATE_BUNDLE_SOURCE,
            "patch": INTERACTIVE_CLI_STATE_BUNDLE_PATCH,
            "changed_turns": changed,
            "scenarios": scenarios,
        }
    return {
        "ok": True,
        "source": INTERACTIVE_CLI_STATE_BUNDLE_SOURCE,
        "patch": INTERACTIVE_CLI_STATE_BUNDLE_PATCH,
        "changed_turns": changed,
        "scenarios": scenarios,
    }
