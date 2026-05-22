from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

# Importing autoplay_llm_campaign loads the late .pyfrag wrappers, including
# N127.2's apply_turn wrapper. This smoke is intentionally short: it verifies
# that LLM-style/freeform autoplay inputs are deterministically promoted to
# backed survival relief commands before the authoritative turn executes.
import tests.rpg.autoplay_llm_campaign  # noqa: F401

from tests.rpg.manual.constants import TEST_RESULTS_ROOT
from tests.rpg.manual.live_survival_seed import DEFAULT_NEEDS, seed_live_survival_session
from tests.rpg.manual.safe import _safe_dict, _safe_int, _safe_list, _safe_str
from tests.rpg.manual.turn_execution import _get_apply_turn

OUT_DIR = TEST_RESULTS_ROOT / "manual-survival-autoplay-llm-smoke"
SUMMARY_PATH = OUT_DIR / "manual-survival-autoplay-llm-smoke-summary.json"
ROWS_PATH = OUT_DIR / "manual-survival-autoplay-llm-smoke-rows.json"

LLM_STYLE_INPUTS = [
    "I continue investigating the road and ask what clue matters next.",
    "I keep following the wagon lead and watch for danger.",
    "I press the investigation forward toward the next useful sign.",
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
    resolved = _safe_dict(sub.get("resolved_result") or sub.get("resolved_action"))
    contract = _safe_dict(result.get("turn_contract"))
    return _first_dict(
        contract.get("climate_survival"),
        resolved.get("climate_survival"),
        sub.get("climate_survival"),
        _safe_dict(_safe_dict(result.get("session")).get("simulation_state")).get("climate_survival"),
    )


def _needs(result: Dict[str, Any]) -> Dict[str, int]:
    climate = _climate(result)
    survival = _safe_dict(climate.get("survival"))
    session = _safe_dict(result.get("session"))
    sim = _safe_dict(session.get("simulation_state"))
    fallback = _safe_dict(sim.get("needs"))
    return {
        "hunger": _safe_int(survival.get("hunger", fallback.get("hunger")), 0),
        "thirst": _safe_int(survival.get("thirst", fallback.get("thirst")), 0),
        "fatigue": _safe_int(survival.get("fatigue", fallback.get("fatigue")), 0),
    }


def _resource_changes(result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(result.get("turn_contract"))
    sub = _result_sub(result)
    resolved = _safe_dict(sub.get("resolved_result") or sub.get("resolved_action"))
    return _first_dict(contract.get("resource_changes"), resolved.get("resource_changes"), sub.get("resource_changes"))


def _survival_action(result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(result.get("turn_contract"))
    changes = _resource_changes(result)
    effect = _first_dict(contract.get("effect_result"), changes.get("effect_result"), _result_sub(result).get("effect_result"))
    return _first_dict(
        contract.get("survival_action"),
        effect.get("survival_action"),
        _safe_dict(changes.get("survival_action")),
    )


def _promotion(result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(result.get("turn_contract"))
    return _first_dict(
        result.get("survival_autoplay_promotion"),
        result.get("survival_autoplay_player_agent"),
        contract.get("survival_autoplay_promotion"),
        contract.get("survival_autoplay_player_agent"),
    )


def _suggestions(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    contract = _safe_dict(result.get("turn_contract"))
    climate = _climate(result)
    rows = _safe_list(contract.get("survival_suggested_actions"))
    rows = rows or _safe_list(contract.get("suggested_actions"))
    rows = rows or _safe_list(climate.get("survival_suggestions"))
    rows = rows or _safe_list(climate.get("suggestions"))
    return [_safe_dict(row) for row in rows if isinstance(row, dict)]


def _row(index: int, original_input: str, result: Dict[str, Any]) -> Dict[str, Any]:
    promotion = _promotion(result)
    action = _survival_action(result)
    changes = _resource_changes(result)
    deltas = _safe_dict(action.get("deltas")) or {
        "hunger_delta": _safe_int(changes.get("hunger_delta"), 0),
        "thirst_delta": _safe_int(changes.get("thirst_delta"), 0),
        "fatigue_delta": _safe_int(changes.get("fatigue_delta"), 0),
    }
    return {
        "turn_index": index,
        "original_player_input": original_input,
        "effective_player_input": _safe_str(promotion.get("effective_player_input") or promotion.get("promoted_player_input")),
        "promotion": promotion,
        "promotion_applied": bool(promotion.get("promoted")),
        "promotion_need": _safe_str(promotion.get("need")),
        "promotion_action_kind": _safe_str(promotion.get("action_kind")),
        "needs": _needs(result),
        "suggestion_count": len(_suggestions(result)),
        "suggestions": _suggestions(result),
        "survival_action": action,
        "relief_applied": bool(action.get("applied")),
        "relief_need": _safe_str(action.get("need")),
        "inventory_consumed": _safe_list(action.get("inventory_consumed")),
        "deltas": deltas,
        "persistence": _safe_dict(result.get("survival_autoplay_persistence")),
        "raw_result_keys": sorted(str(key) for key in _safe_dict(result).keys()),
    }


def _summarize(session_id: str, rows: List[Dict[str, Any]], errors: List[str]) -> Dict[str, Any]:
    promoted_rows = [row for row in rows if row.get("promotion_applied")]
    relief_rows = [row for row in rows if row.get("relief_applied")]
    suggestion_rows = [row for row in rows if _safe_int(row.get("suggestion_count"), 0) > 0]
    consumed_count = sum(len(_safe_list(row.get("inventory_consumed"))) for row in rows)
    relief_needs = sorted({_safe_str(row.get("relief_need")) for row in relief_rows if _safe_str(row.get("relief_need"))})
    promotion_needs = sorted({_safe_str(row.get("promotion_need")) for row in promoted_rows if _safe_str(row.get("promotion_need"))})
    final_needs = _safe_dict(rows[-1].get("needs")) if rows else {}
    failures: List[str] = []
    if len(promoted_rows) < 3:
        failures.append("missing_three_survival_promotions")
    if len(relief_rows) < 3:
        failures.append("missing_three_relief_actions")
    if len(suggestion_rows) < 2:
        failures.append("missing_backed_survival_suggestions")
    if consumed_count < 2:
        failures.append("missing_food_and_water_inventory_consumption")
    for need in ("thirst", "hunger", "fatigue"):
        if need not in promotion_needs:
            failures.append(f"missing_{need}_promotion")
        if need not in relief_needs:
            failures.append(f"missing_{need}_relief")
    if _safe_int(final_needs.get("thirst"), 999) >= DEFAULT_NEEDS["thirst"]:
        failures.append("thirst_not_reduced")
    if _safe_int(final_needs.get("hunger"), 999) >= DEFAULT_NEEDS["hunger"]:
        failures.append("hunger_not_reduced")
    if _safe_int(final_needs.get("fatigue"), 999) >= DEFAULT_NEEDS["fatigue"]:
        failures.append("fatigue_not_reduced")

    return {
        "format_version": "n1272_survival_autoplay_llm_smoke_v1",
        "ok": not errors and not failures,
        "session_id": session_id,
        "turns_requested": len(LLM_STYLE_INPUTS),
        "turns_executed": len(rows),
        "starting_needs": dict(DEFAULT_NEEDS),
        "final_needs": final_needs,
        "promotion_count": len(promoted_rows),
        "promotion_needs": promotion_needs,
        "relief_applied_count": len(relief_rows),
        "relief_needs": relief_needs,
        "survival_suggestion_rows": len(suggestion_rows),
        "inventory_consumed_count": consumed_count,
        "source_gate": {
            "gate": "n1272_targeted_llm_survival_autoplay_ok",
            "ok": not failures,
            "advisory_only": False,
            "source": "manual_survival_autoplay_llm_smoke",
            "reasons": failures,
            "coverage": {
                "row_count": len(rows),
                "promotion_rows": len(promoted_rows),
                "relief_rows": len(relief_rows),
                "suggestion_rows": len(suggestion_rows),
                "inventory_consumed_count": consumed_count,
            },
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
    for index, player_input in enumerate(LLM_STYLE_INPUTS, start=1):
        try:
            result = _safe_dict(apply_turn(session_id=session_id, player_input=player_input))
            rows.append(_row(index, player_input, result))
        except Exception as exc:
            errors.append(f"turn_{index}:{type(exc).__name__}:{exc}")
            break
    summary = _summarize(session_id, rows, errors)
    _write_json(ROWS_PATH, rows)
    _write_json(SUMMARY_PATH, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="N127.2 targeted LLM-style survival autoplay smoke.")
    parser.add_argument("--session-id", default="", help="Optional stable manual session id.")
    args = parser.parse_args()
    session_id = args.session_id.strip() or f"manual_survival_autoplay_llm_smoke_{_utc_stamp()}"
    summary = run_smoke(session_id)
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
