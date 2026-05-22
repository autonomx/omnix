from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.rpg.session.service import save_session
from tests.rpg.manual.constants import TEST_RESULTS_ROOT
from tests.rpg.manual.live_survival_seed import DEFAULT_NEEDS, seed_live_survival_session
from tests.rpg.manual.safe import _safe_dict, _safe_int, _safe_list, _safe_str
from tests.rpg.manual.turn_execution import _get_apply_turn

OUT_DIR = TEST_RESULTS_ROOT / "manual-survival-live-relief-smoke"
SUMMARY_PATH = OUT_DIR / "manual-survival-live-relief-smoke-summary.json"
ROWS_PATH = OUT_DIR / "manual-survival-live-relief-smoke-rows.json"

COMMANDS = [
    "I pause and check what my body needs.",
    "I drink from the waterskin.",
    "I eat the trail ration.",
    "I rest for a while.",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _write_json(path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _result_sub(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(result).get("result"))


def _climate(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    sub = _result_sub(result)
    resolved = _safe_dict(sub.get("resolved_result"))
    contract = _safe_dict(result.get("turn_contract"))
    return _first_dict(
        contract.get("climate_survival"),
        sub.get("climate_survival"),
        resolved.get("climate_survival"),
        _safe_dict(result.get("session")).get("climate_survival"),
    )


def _resource_changes(result: Dict[str, Any]) -> Dict[str, Any]:
    sub = _result_sub(result)
    resolved = _safe_dict(sub.get("resolved_result"))
    climate = _climate(result)
    return _first_dict(
        _safe_dict(climate.get("resource_changes")),
        sub.get("resource_changes"),
        resolved.get("resource_changes"),
    )


def _survival_action(result: Dict[str, Any]) -> Dict[str, Any]:
    sub = _result_sub(result)
    resolved = _safe_dict(sub.get("resolved_result"))
    climate = _climate(result)
    changes = _resource_changes(result)
    return _first_dict(
        _safe_dict(_safe_dict(changes.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(sub.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(resolved.get("effect_result")).get("survival_action")),
        _safe_dict(_safe_dict(climate.get("effect_result")).get("survival_action")),
    )


def _suggestions(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    climate = _climate(result)
    sub = _result_sub(result)
    contract = _safe_dict(_safe_dict(result).get("turn_contract"))
    rows = _safe_list(climate.get("survival_suggestions")) or _safe_list(climate.get("suggestions"))
    rows = rows or _safe_list(sub.get("survival_suggestions"))
    rows = rows or _safe_list(contract.get("suggested_actions"))
    return [_safe_dict(row) for row in rows if isinstance(row, dict) and (_safe_str(_safe_dict(row).get("kind")) in ("", "survival_relief"))]


def _needs(result: Dict[str, Any]) -> Dict[str, int]:
    climate = _climate(result)
    survival = _safe_dict(climate.get("survival"))
    session = _safe_dict(_safe_dict(result).get("session"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    fallback = _safe_dict(simulation_state.get("needs"))
    return {
        "hunger": _safe_int(survival.get("hunger", fallback.get("hunger")), 0),
        "thirst": _safe_int(survival.get("thirst", fallback.get("thirst")), 0),
        "fatigue": _safe_int(survival.get("fatigue", fallback.get("fatigue")), 0),
    }


def _inventory(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    session = _safe_dict(_safe_dict(result).get("session"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    return [_safe_dict(item) for item in _safe_list(inventory_state.get("items")) if isinstance(item, dict)]


def _row(index: int, command: str, result: Dict[str, Any]) -> Dict[str, Any]:
    action = _survival_action(result)
    changes = _resource_changes(result)
    deltas = _safe_dict(action.get("deltas")) or {
        "hunger_delta": _safe_int(changes.get("hunger_delta"), 0),
        "thirst_delta": _safe_int(changes.get("thirst_delta"), 0),
        "fatigue_delta": _safe_int(changes.get("fatigue_delta"), 0),
    }
    suggestions = _suggestions(result)
    return {
        "turn_index": index,
        "player_input": command,
        "needs": _needs(result),
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
        "survival_action": action,
        "relief_applied": bool(action.get("applied")),
        "relief_need": _safe_str(action.get("need")),
        "deltas": deltas,
        "inventory_consumed": _safe_list(action.get("inventory_consumed")),
        "inventory_after": _inventory(result),
        "raw_result_keys": sorted(str(key) for key in _safe_dict(result).keys()),
    }


def _summarize(session_id: str, rows: List[Dict[str, Any]], errors: List[str]) -> Dict[str, Any]:
    final_needs = _safe_dict(rows[-1].get("needs")) if rows else {}
    relief_rows = [row for row in rows if row.get("relief_applied")]
    consumed_rows = [row for row in rows if _safe_list(row.get("inventory_consumed"))]
    suggestion_rows = [row for row in rows if _safe_int(row.get("suggestion_count"), 0) > 0]
    negative_rows = [
        row for row in rows
        if any(_safe_int(_safe_dict(row.get("deltas")).get(key), 0) < 0 for key in ("hunger_delta", "thirst_delta", "fatigue_delta"))
    ]
    relief_needs = sorted({_safe_str(row.get("relief_need")) for row in relief_rows if _safe_str(row.get("relief_need"))})
    failures: List[str] = []
    if not suggestion_rows:
        failures.append("missing_survival_suggestion_rows")
    for need in ("thirst", "hunger", "fatigue"):
        if need not in relief_needs:
            failures.append(f"missing_{need}_relief")
    if len(consumed_rows) < 2:
        failures.append("missing_inventory_consumption_for_food_and_water")
    if len(negative_rows) < 3:
        failures.append("missing_negative_survival_deltas")
    if _safe_int(final_needs.get("thirst"), 999) >= DEFAULT_NEEDS["thirst"]:
        failures.append("thirst_not_reduced")
    if _safe_int(final_needs.get("hunger"), 999) >= DEFAULT_NEEDS["hunger"]:
        failures.append("hunger_not_reduced")
    if _safe_int(final_needs.get("fatigue"), 999) >= DEFAULT_NEEDS["fatigue"]:
        failures.append("fatigue_not_reduced")
    return {
        "format_version": "n1263_manual_survival_live_relief_smoke_v3",
        "ok": not errors and not failures,
        "session_id": session_id,
        "turns_requested": len(COMMANDS),
        "turns_executed": len(rows),
        "starting_needs": dict(DEFAULT_NEEDS),
        "final_needs": final_needs,
        "survival_suggestion_rows": len(suggestion_rows),
        "relief_applied_count": len(relief_rows),
        "inventory_consumed_count": sum(len(_safe_list(row.get("inventory_consumed"))) for row in rows),
        "negative_delta_rows": len(negative_rows),
        "relief_needs": relief_needs,
        "source_gate": {
            "gate": "live_runtime_survival_suggestions_and_relief",
            "ok": not failures,
            "advisory_only": False,
            "source": "n1263_live_runtime_survival_repair",
            "coverage": {
                "row_count": len(rows),
                "survival_suggestion_rows": len(suggestion_rows),
                "relief_applied_rows": len(relief_rows),
                "inventory_consumed_rows": len(consumed_rows),
                "negative_delta_rows": len(negative_rows),
            },
            "reasons": failures,
        },
        "artifact_files": {"summary": SUMMARY_PATH.name, "rows": ROWS_PATH.name},
        "errors": errors,
        "validation_failures": failures,
    }


def run_smoke(session_id: str) -> Dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seed_live_survival_session(session_id, reset_first=True)
    apply_turn = _get_apply_turn()
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, command in enumerate(COMMANDS, start=1):
        try:
            result = _safe_dict(apply_turn(session_id=session_id, player_input=command))
            session = _safe_dict(result.get("session"))
            if session:
                save_session(session)
            rows.append(_row(index, command, result))
        except Exception as exc:
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
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
