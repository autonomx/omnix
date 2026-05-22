from __future__ import annotations

"""N126.1 short survival pressure/relief smoke.

Runs a compact live-runtime scenario that avoids 100-turn autoplay while proving
this loop:

    seeded pressure -> warnings/suggestions -> eat/drink/rest relief -> metrics

Example:
    python src/tests/rpg/manual_survival_relief_smoke.py --require-llm
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
    _save_manual_session_for_test,
    _sync_manual_simulation_state,
)
from tests.rpg.manual.turn_execution import _get_apply_turn  # noqa: E402
from tests.rpg.manual_survival_source_smoke import (  # noqa: E402
    _build_row,
    _safe_dict,
)

RESULT_ROOT = Path("resources/data/test-results/manual-survival-relief-smoke")
DEFAULT_TURNS = [
    "I wait and listen while checking my hunger, thirst, and fatigue.",
    "I drink my waterskin.",
    "I eat my trail ration.",
    "I rest by the hearth.",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _player_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    simulation_state["player_state"] = player_state
    return player_state


def _seed_pressure_session(session_id: str) -> Dict[str, Any]:
    session = _ensure_manual_session(session_id)
    simulation_state = _safe_dict(session.get("simulation_state"))
    session["simulation_state"] = simulation_state
    simulation_state["location_id"] = "loc_tavern"
    simulation_state["current_location_id"] = "loc_tavern"

    player_state = _player_state(simulation_state)
    player_state["location_id"] = "loc_tavern"
    player_state["current_location_id"] = "loc_tavern"
    player_state["resources"] = {"hunger": 80, "thirst": 82, "fatigue": 78}
    player_state["inventory_state"] = {
        "items": [
            {"item_id": "trail_ration", "name": "Trail Ration", "quantity": 1, "tags": ["food", "ration"]},
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ],
        "currency": {"gold": 1, "silver": 10, "copper": 20},
        "capacity": 50,
        "equipment": {},
        "last_loot": [],
    }
    simulation_state["climate_survival"] = {
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
    }
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["tick"] = 0
    runtime_state["last_turn_contract"] = {}
    runtime_state["last_turn_result"] = {}
    session["runtime_state"] = runtime_state
    _sync_manual_simulation_state(session)
    _save_manual_session_for_test(session_id, session)
    return session


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
    _reset_manual_session_artifacts(session_id)
    _seed_pressure_session(session_id)
    apply_turn = _get_apply_turn()

    raw_rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, player_input in enumerate(DEFAULT_TURNS, start=1):
        try:
            result = apply_turn(session_id=session_id, player_input=player_input)
            raw_rows.append(_build_row(index, player_input, _safe_dict(result)))
        except Exception as exc:  # pragma: no cover - live smoke diagnostic path
            errors.append(f"turn_{index}:{type(exc).__name__}:{exc}")
            break

    projected_rows = persist_survival_evidence_into_transcript_rows(raw_rows)
    source_summary = build_survival_metric_source_summary(projected_rows)
    source_gate = build_survival_metric_source_gate(source_summary)
    pressure_summary = build_survival_pressure_relief_summary(projected_rows)
    llm_called_count = sum(1 for row in projected_rows if bool(row.get("llm_called")))
    validation_failures = _validate_relief_summary(
        source_gate=source_gate,
        pressure_summary=pressure_summary,
        require_llm=require_llm,
        llm_called_count=llm_called_count,
    )
    ok = not errors and not validation_failures
    summary = {
        "format_version": "n1261_manual_survival_relief_smoke_v1",
        "ok": ok,
        "session_id": session_id,
        "turns_executed": len(projected_rows),
        "turns_requested": len(DEFAULT_TURNS),
        "llm_called_count": llm_called_count,
        "require_llm": require_llm,
        "errors": errors,
        "validation_failures": validation_failures,
        "source_gate": source_gate,
        "source_summary": source_summary,
        "pressure_summary": {key: value for key, value in pressure_summary.items() if key not in {"trend_rows"}},
    }

    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-summary.json", summary)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-rows.json", projected_rows)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-source-summary.json", source_summary)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-source-gate.json", source_gate)
    _write_json(RESULT_ROOT / "manual-survival-relief-smoke-pressure-summary.json", pressure_summary)
    return summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run short N126.1 survival pressure/relief smoke.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to smoke timestamp/uuid.")
    parser.add_argument("--require-llm", action="store_true", help="Fail if no turn reports an LLM/provider call.")
    args = parser.parse_args(argv)

    session_id = args.session_id.strip() or f"manual_survival_relief_smoke_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    summary = run_relief_smoke(session_id=session_id, require_llm=bool(args.require_llm))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
