from __future__ import annotations

"""N126.1 short survival pressure/relief smoke.

Runs a compact scenario that avoids 100-turn autoplay while proving this loop:

    seeded pressure -> warnings/suggestions -> eat/drink/rest relief -> metrics

The script uses one live apply_turn call to prove the LLM/provider path when
``--require-llm`` is set, then validates relief with the deterministic survival
runtime functions directly. This avoids slow campaign runs and avoids manual
session persistence differences from masking the survival logic under test.

Example:
    python src/tests/rpg/manual_survival_relief_smoke.py --require-llm
"""

import argparse
import json
import sys
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.rpg.session.runtime_promotions import apply_climate_survival_turn_effects  # noqa: E402
from app.rpg.session.survival_actions import (  # noqa: E402
    build_survival_suggested_actions,
    resolve_survival_action,
)
from app.rpg.session.survival_metrics import (  # noqa: E402
    build_survival_metric_source_gate,
    build_survival_metric_source_summary,
    build_survival_pressure_relief_summary,
)
from app.rpg.session.survival_transcript_projector import (  # noqa: E402
    persist_survival_evidence_into_transcript_rows,
)
from tests.rpg.manual.session_helpers import (  # noqa: E402
    _ensure_manual_session,
    _reset_manual_session_artifacts,
)
from tests.rpg.manual.turn_execution import _get_apply_turn  # noqa: E402
from tests.rpg.manual_survival_source_smoke import (  # noqa: E402
    _build_row,
    _safe_dict,
)

RESULT_ROOT = Path("resources/data/test-results/manual-survival-relief-smoke")
LIVE_LLM_PROBE_TURN = "I pause and check how tired, hungry, and thirsty I feel."
RELIEF_TURNS = [
    "I wait and listen while checking my hunger, thirst, and fatigue.",
    "I drink my waterskin.",
    "I eat my trail ration.",
    "I rest by the hearth.",
]


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _seeded_survival_state() -> Dict[str, Any]:
    return {
        "location_id": "loc_tavern",
        "current_location_id": "loc_tavern",
        "player_state": {
            "location_id": "loc_tavern",
            "current_location_id": "loc_tavern",
            "resources": {"hunger": 80, "thirst": 82, "fatigue": 78},
            "inventory_state": {
                "items": [
                    {"item_id": "trail_ration", "name": "Trail Ration", "quantity": 1, "tags": ["food", "ration"]},
                    {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
                ],
                "currency": {"gold": 1, "silver": 10, "copper": 20},
                "capacity": 50,
                "equipment": {},
                "last_loot": [],
            },
        },
        "climate_survival": {
            "format_version": "n1231_climate_survival_state_v1",
            "runtime_enforced": True,
            "source": "n1261_seeded_survival_pressure_smoke",
            "tick": 0,
            "minutes_per_turn": 15,
            "survival": {
                "hunger": 80,
                "thirst": 82,
                "fatigue": 78,
                "warnings": ["hunger_high", "thirst_high", "fatigue_high"],
            },
        },
    }


def _merge_resource_changes(climate_changes: Dict[str, Any], relief_changes: Dict[str, Any]) -> Dict[str, Any]:
    climate_changes = _safe_dict(climate_changes)
    relief_changes = _safe_dict(relief_changes)
    if climate_changes and relief_changes:
        return {
            "source": "merged_turn_resource_changes",
            "sources": ["n1231_climate_survival_tick", "n1232_survival_action_resolution"],
            "climate_survival": climate_changes,
            "survival_action": relief_changes,
        }
    return climate_changes or relief_changes or {}


def _merge_effect_result(climate_effect: Dict[str, Any], relief_effect: Dict[str, Any]) -> Dict[str, Any]:
    climate_effect = _safe_dict(climate_effect)
    relief_effect = _safe_dict(relief_effect)
    if climate_effect and relief_effect:
        warnings = list(dict.fromkeys(_safe_list(climate_effect.get("warnings")) + _safe_list(relief_effect.get("warnings"))))
        return {
            "source": "merged_turn_effect_result",
            "sources": ["n1231_climate_survival_tick", "n1232_survival_action_resolution"],
            "applied": bool(climate_effect.get("applied") or relief_effect.get("applied")),
            "effects": _safe_list(climate_effect.get("effects")) + _safe_list(relief_effect.get("effects")),
            "warnings": warnings,
            "climate_survival": climate_effect,
            "survival_action": relief_effect,
        }
    return climate_effect or relief_effect or {}


def _build_relief_row(
    *,
    turn_index: int,
    player_input: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    tick_result = apply_climate_survival_turn_effects(simulation_state, runtime_state)
    suggestions = build_survival_suggested_actions(simulation_state, runtime_state)
    relief_result = resolve_survival_action(
        player_input=player_input,
        simulation_state=simulation_state,
        service_result={},
    )
    climate_survival = _safe_dict(simulation_state.get("climate_survival") or tick_result.get("climate_survival"))
    resource_changes = _merge_resource_changes(
        _safe_dict(tick_result.get("resource_changes")),
        _safe_dict(_safe_dict(relief_result).get("resource_changes")),
    )
    effect_result = _merge_effect_result(
        _safe_dict(tick_result.get("effect_result")),
        _safe_dict(_safe_dict(relief_result).get("effect_result")),
    )
    turn_contract = {
        "version": "turn_contract_v1_n1261_smoke",
        "player_input": player_input,
        "climate_survival": climate_survival,
        "resource_changes": resource_changes,
        "effect_result": effect_result,
        "survival_action": _safe_dict(relief_result),
        "survival_suggested_actions": suggestions,
        "suggested_actions": suggestions,
        "presentation": {
            "survival_suggested_actions": suggestions,
            "available_actions": suggestions,
        },
    }
    return {
        "turn_index": turn_index,
        "player": player_input,
        "turn_contract": turn_contract,
        "climate_survival": climate_survival,
        "resource_changes": resource_changes,
        "effect_result": effect_result,
        "survival_action": _safe_dict(relief_result),
        "survival_suggested_actions": suggestions,
        "suggested_actions": suggestions,
        "llm_called": False,
        "source": "n1261_deterministic_survival_relief_smoke",
    }


def _build_deterministic_relief_rows() -> List[Dict[str, Any]]:
    simulation_state = _seeded_survival_state()
    runtime_state = {"tick": 0}
    rows: List[Dict[str, Any]] = []
    for index, player_input in enumerate(RELIEF_TURNS, start=1):
        rows.append(
            _build_relief_row(
                turn_index=index,
                player_input=player_input,
                simulation_state=simulation_state,
                runtime_state=runtime_state,
            )
        )
    return rows


def _run_live_llm_probe(session_id: str) -> List[Dict[str, Any]]:
    _reset_manual_session_artifacts(session_id)
    _ensure_manual_session(session_id)
    apply_turn = _get_apply_turn()
    result = apply_turn(session_id=session_id, player_input=LIVE_LLM_PROBE_TURN)
    return [_build_row(1, LIVE_LLM_PROBE_TURN, _safe_dict(result))]


def _coverage_counts(summary: Dict[str, Any]) -> Dict[str, int]:
    return _safe_dict(_safe_dict(summary.get("source_coverage_summary")).get("coverage"))


def _validate_relief_summary(*, source_gate: Dict[str, Any], pressure_summary: Dict[str, Any], require_llm: bool, llm_called_count: int) -> List[str]:
    failures: List[str] = []
    coverage = _coverage_counts(pressure_summary)
    if not source_gate.get("ok"):
        failures.append("survival_source_gate_failed")
    if int(pressure_summary.get("survival_warning_count") or 0) <= 0:
        failures.append("missing_survival_warnings")
    if int(coverage.get("survival_suggestion_rows") or 0) <= 0:
        failures.append("missing_survival_suggestions")
    if int(pressure_summary.get("relief_action_count") or 0) < 3:
        failures.append("missing_expected_relief_actions")
    net = _safe_dict(pressure_summary.get("net_resource_deltas"))
    if int(net.get("hunger_delta") or 0) >= 0:
        failures.append("missing_hunger_relief_delta")
    if int(net.get("thirst_delta") or 0) >= 0:
        failures.append("missing_thirst_relief_delta")
    if int(net.get("fatigue_delta") or 0) >= 0:
        failures.append("missing_fatigue_relief_delta")
    consumed = pressure_summary.get("inventory_consumed_summary") or []
    consumed_ids = {str(_safe_dict(item).get("item_id") or "") for item in consumed}
    if "trail_ration" not in consumed_ids:
        failures.append("trail_ration_not_consumed")
    if "waterskin" not in consumed_ids:
        failures.append("waterskin_not_consumed")
    if require_llm and llm_called_count <= 0:
        failures.append("llm_not_detected")
    return failures


def run_relief_smoke(*, session_id: str, require_llm: bool) -> Dict[str, Any]:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    errors: List[str] = []
    live_rows: List[Dict[str, Any]] = []
    if require_llm:
        try:
            live_rows = _run_live_llm_probe(f"{session_id}_llm_probe")
        except Exception as exc:  # pragma: no cover - live smoke diagnostic path
            errors.append(f"llm_probe:{type(exc).__name__}:{exc}")

    relief_rows = _build_deterministic_relief_rows()
    projected_relief_rows = persist_survival_evidence_into_transcript_rows(relief_rows)
    projected_live_rows = persist_survival_evidence_into_transcript_rows(live_rows)
    source_summary = build_survival_metric_source_summary(projected_relief_rows)
    source_gate = build_survival_metric_source_gate(source_summary)
    pressure_summary = build_survival_pressure_relief_summary(projected_relief_rows)
    llm_called_count = sum(1 for row in projected_live_rows if bool(row.get("llm_called")))
    validation_failures = _validate_relief_summary(
        source_gate=source_gate,
        pressure_summary=pressure_summary,
        require_llm=require_llm,
        llm_called_count=llm_called_count,
    )
    ok = not errors and not validation_failures
    summary = {
        "format_version": "n1261_manual_survival_relief_smoke_v2",
        "ok": ok,
        "session_id": session_id,
        "turns_executed": len(projected_relief_rows),
        "turns_requested": len(RELIEF_TURNS),
        "live_turns_executed": len(projected_live_rows),
        "llm_called_count": llm_called_count,
        "require_llm": require_llm,
        "errors": errors,
        "validation_failures": validation_failures,
        "source_gate": source_gate,
        "source_summary": source_summary,
        "pressure_summary": {key: value for key, value in pressure_summary.items() if key not in {"trend_rows"}},
    }

    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-summary.json", summary)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-rows.json", projected_relief_rows)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-live-rows.json", projected_live_rows)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-source-summary.json", source_summary)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-source-gate.json", source_gate)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-pressure-summary.json", pressure_summary)
    return summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run short N126.1 survival pressure/relief smoke.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to smoke timestamp/uuid.")
    parser.add_argument("--require-llm", action="store_true", help="Run one live turn and fail if no LLM/provider call is detected.")
    args = parser.parse_args(argv)

    session_id = args.session_id.strip() or f"manual_survival_relief_smoke_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    summary = run_relief_smoke(session_id=session_id, require_llm=bool(args.require_llm))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
