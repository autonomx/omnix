from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from tests.rpg.manual.constants import TEST_RESULTS_ROOT
from tests.rpg.manual.safe import _safe_dict, _safe_int, _safe_list, _safe_str
from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _save_manual_session_for_test,
)
from tests.rpg.manual.turn_execution import _get_apply_turn

OUT_DIR = TEST_RESULTS_ROOT / "manual-survival-live-relief-smoke"
SUMMARY_PATH = OUT_DIR / "manual-survival-live-relief-smoke-summary.json"
ROWS_PATH = OUT_DIR / "manual-survival-live-relief-smoke-rows.json"

STARTING_NEEDS = {"hunger": 80, "thirst": 82, "fatigue": 78}
SURVIVAL_COMMANDS = [
    "I pause and check what my body needs.",
    "I drink from the waterskin.",
    "I eat the trail ration.",
    "I rest for a while.",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _write_json(path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _seed_live_survival_session(session_id: str) -> Dict[str, Any]:
    session = _ensure_manual_session(session_id)
    simulation_state = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))

    inventory_state["items"] = [
        {
            "item_id": "trail_ration",
            "name": "Trail Ration",
            "quantity": 1,
            "tags": ["food", "ration"],
        },
        {
            "item_id": "waterskin",
            "name": "Waterskin",
            "quantity": 1,
            "tags": ["drink", "water"],
        },
    ]
    inventory_state["currency"] = {"gold": 1, "silver": 10, "copper": 20}
    player_state["inventory_state"] = inventory_state
    player_state["inventory"] = {"items": deepcopy(inventory_state["items"])}

    climate_survival = {
        "format_version": "n1263_climate_survival_state_v1",
        "runtime_enforced": True,
        "source": "n1263_live_runtime_survival_seed",
        "minutes_per_turn": 15,
        "tick": 0,
        "survival": {
            **STARTING_NEEDS,
            "warnings": ["hunger_high", "thirst_high", "fatigue_high"],
        },
    }
    simulation_state["needs"] = dict(STARTING_NEEDS)
    simulation_state["climate_survival"] = deepcopy(climate_survival)
    simulation_state.setdefault("location_id", "loc_tavern")
    simulation_state.setdefault("current_location_id", "loc_tavern")
    player_state["needs"] = dict(STARTING_NEEDS)
    player_state["climate_survival"] = deepcopy(climate_survival)
    player_state.setdefault("location_id", "loc_tavern")
    player_state.setdefault("current_location_id", "loc_tavern")
    simulation_state["player_state"] = player_state

    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state.setdefault("runtime_settings", {})
    runtime_state.setdefault("last_turn_result", {})
    runtime_state["tick"] = 0
    session["runtime_state"] = runtime_state
    session["simulation_state"] = simulation_state

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload

    _save_manual_session_for_test(session_id, session)
    return session


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _extract_survival_action(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    resolved = _safe_dict(result_sub.get("resolved_result"))
    climate = _first_dict(
        turn_contract.get("climate_survival"),
        result_sub.get("climate_survival"),
        resolved.get("climate_survival"),
    )
    resource_changes = _first_dict(
        _safe_dict(climate.get("resource_changes")),
        result_sub.get("resource_changes"),
        resolved.get("resource_changes"),
    )
    return _first_dict(
        _safe_dict(_safe_dict(resource_changes.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(result_sub.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(resolved.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(climate.get("effect_result")).get("survival_action")),
    )


def _extract_climate(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    resolved = _safe_dict(result_sub.get("resolved_result"))
    return _first_dict(
        turn_contract.get("climate_survival"),
        result_sub.get("climate_survival"),
        resolved.get("climate_survival"),
    )


def _extract_suggestions(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    climate = _extract_climate(result)
    suggestions = _safe_list(climate.get("survival_suggestions")) or _safe_list(climate.get("suggestions"))
    if suggestions:
        return [_safe_dict(row) for row in suggestions if isinstance(row, dict)]
    return [
        _safe_dict(row)
        for row in _safe_list(result_sub.get("survival_suggestions")) + _safe_list(turn_contract.get("suggested_actions"))
        if isinstance(row, dict) and _safe_str(_safe_dict(row).get("kind")) == "survival_relief"
    ]


def _extract_needs(result: Dict[str, Any]) -> Dict[str, int]:
    climate = _extract_climate(result)
    survival = _safe_dict(climate.get("survival"))
    session = _safe_dict(result.get("session"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    fallback = _safe_dict(simulation_state.get("needs"))
    return {
        "hunger": _safe_int(survival.get("hunger", fallback.get("hunger")), 0),
        "thirst": _safe_int(survival.get("thirst", fallback.get("thirst")), 0),
        "fatigue": _safe_int(survival.get("fatigue", fallback.get("fatigue")), 0),
    }


def _extract_inventory(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    session = _safe_dict(_safe_dict(result).get("session"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    return [_safe_dict(item) for item in _safe_list(inventory_state.get("items")) if isinstance(item, dict)]


def _extract_row(turn_index: int, player_input: str, result: Dict[str, Any]) -> Dict[str, Any]:
    climate = _extract_climate(result)
    suggestions = _extract_suggestions(result)
    survival_action = _extract_survival_action(result)
    needs = _extract_needs(result)
    resource_changes = _first_dict(
        _safe_dict(climate.get("resource_changes")),
        _safe_dict(_safe_dict(result).get("result")).get("resource_changes"),
    )
    deltas = _safe_dict(survival_action.get("deltas"))
    if not deltas:
        deltas = {
            "hunger_delta": _safe_int(resource_changes.get("hunger_delta"), 0),
            "thirst_delta": _safe_int(resource_changes.get("thirst_delta"), 0),
            "fatigue_delta": _safe_int(resource_changes.get("fatigue_delta"), 0),
        }
    return {
        "turn_index": turn_index,
        "player_input": player_input,
        "ok": bool(_safe_dict(result).get("ok", True)),
        "needs": needs,
        "warnings": _safe_list(climate.get("warnings") or _safe_dict(climate.get("survival")).get("warnings")),
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
        "survival_action": survival_action,
        "relief_applied": bool(survival_action.get("applied")),
        "relief_need": _safe_str(survival_action.get("need")),
        "deltas": deltas,
        "inventory_consumed": _safe_list(survival_action.get("inventory_consumed")),
        "inventory_after": _extract_inventory(result),
        "source_gate": _safe_dict(climate.get("source_gate")),
        "raw_result_keys": sorted([str(k) for k in _safe_dict(result).keys()]),
    }


def _summarize(session_id: str, rows: List[Dict[str, Any]], errors: List[str]) -> Dict[str, Any]:
    final_needs = _safe_dict(rows[-1].get("needs")) if rows else {}
    relief_rows = [row for row in rows if row.get("relief_applied")]
    consumed_rows = [row for row in rows if _safe_list(row.get("inventory_consumed"))]
    suggestion_rows = [row for row in rows if _safe_int(row.get("suggestion_count"), 0) > 0]
    negative_delta_rows = [
        row for row in rows
        if any(_safe_int(_safe_dict(row.get("deltas")).get(key), 0) < 0 for key in ("hunger_delta", "thirst_delta", "fatigue_delta"))
    ]
    relief_needs = sorted({_safe_str(row.get("relief_need")) for row in relief_rows if _safe_str(row.get("relief_need"))})

    validation_failures: List[str] = []
    if not suggestion_rows:
        validation_failures.append("missing_survival_suggestion_rows")
    for need in ("thirst", "hunger", "fatigue"):
        if need not in relief_needs:
            validation_failures.append(f"missing_{need}_relief")
    if len(consumed_rows) < 2:
        validation_failures.append("missing_inventory_consumption_for_food_and_water")
    if len(negative_delta_rows) < 3:
        validation_failures.append("missing_negative_survival_deltas")
    if _safe_int(final_needs.get("thirst"), 999) >= STARTING_NEEDS["thirst"]:
        validation_failures.append("thirst_not_reduced")
    if _safe_int(final_needs.get("hunger"), 999) >= STARTING_NEEDS["hunger"]:
        validation_failures.append("hunger_not_reduced")
    if _safe_int(final_needs.get("fatigue"), 999) >= STARTING_NEEDS["fatigue"]:
        validation_failures.append("fatigue_not_reduced")

    return {
        "format_version": "n1263_manual_survival_live_relief_smoke_v1",
        "ok": not errors and not validation_failures,
        "session_id": session_id,
        "turns_requested": len(SURVIVAL_COMMANDS),
        "turns_executed": len(rows),
        "starting_needs": dict(STARTING_NEEDS),
        "final_needs": final_needs,
        "survival_suggestion_rows": len(suggestion_rows),
        "relief_applied_count": len(relief_rows),
        "inventory_consumed_count": sum(len(_safe_list(row.get("inventory_consumed"))) for row in rows),
        "negative_delta_rows": len(negative_delta_rows),
        "relief_needs": relief_needs,
        "source_gate": {
            "gate": "live_runtime_survival_suggestions_and_relief",
            "ok": not validation_failures,
            "advisory_only": False,
            "source": "n1263_live_runtime_survival_repair",
            "coverage": {
                "row_count": len(rows),
                "survival_suggestion_rows": len(suggestion_rows),
                "relief_applied_rows": len(relief_rows),
                "inventory_consumed_rows": len(consumed_rows),
                "negative_delta_rows": len(negative_delta_rows),
            },
            "reasons": validation_failures,
        },
        "artifact_files": {
            "summary": SUMMARY_PATH.name,
            "rows": ROWS_PATH.name,
        },
        "errors": errors,
        "validation_failures": validation_failures,
    }


def run_smoke(session_id: str) -> Dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _seed_live_survival_session(session_id)
    apply_turn = _get_apply_turn()
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []

    for index, command in enumerate(SURVIVAL_COMMANDS, start=1):
        try:
            result = apply_turn(session_id=session_id, player_input=command)
            result = _safe_dict(result)
            if _safe_dict(result.get("session")):
                _save_manual_session_for_test(session_id, _safe_dict(result.get("session")))
            rows.append(_extract_row(index, command, result))
        except Exception as exc:  # pragma: no cover - smoke artifact path
            errors.append(f"turn_{index}:{type(exc).__name__}:{exc}")
            break

    summary = _summarize(session_id, rows, errors)
    _write_json(ROWS_PATH, rows)
    _write_json(SUMMARY_PATH, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="N126.3 live survival suggestions and relief smoke.")
    parser.add_argument("--session-id", default="", help="Optional stable manual session id.")
    args = parser.parse_args()
    session_id = args.session_id.strip() or f"manual_survival_live_relief_smoke_{_utc_stamp()}"
    summary = run_smoke(session_id)
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
