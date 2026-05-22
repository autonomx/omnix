from __future__ import annotations

"""Short live-runtime/LLM smoke for N125 survival source evidence.

This is intentionally much cheaper than a 100-turn autoplay campaign. It runs a
few real apply_turn calls, extracts the same survival source metrics used by the
100-turn report, writes compact artifacts, and exits non-zero when survival
source evidence is missing.

Example:
    python src/tests/rpg/manual_survival_source_smoke.py --turns 3 --require-llm
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Preserve direct-script behavior like manual_llm_transcript.py.
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
)
from tests.rpg.manual.turn_execution import _get_apply_turn  # noqa: E402

RESULT_ROOT = Path("resources/data/test-results/manual-survival-source-smoke")
DEFAULT_TURNS = [
    "I pause and check how tired, hungry, and thirsty I feel.",
    "I wait and listen for a moment.",
    "I ask Bran what food, water, or a room would cost if I need rest.",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_turn_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    return _safe_dict(
        result.get("turn_contract")
        or _safe_dict(result.get("result")).get("turn_contract")
        or _safe_dict(result.get("authoritative_result")).get("turn_contract")
    )


def _extract_climate_survival(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    contract = _extract_turn_contract(result)
    candidates = [
        result.get("climate_survival"),
        contract.get("climate_survival"),
        _safe_dict(result.get("result")).get("climate_survival"),
        _safe_dict(result.get("presentation")).get("climate_survival"),
        _safe_dict(result.get("runtime_promotion_panel")).get("climate_survival"),
        _safe_dict(_safe_dict(result.get("result")).get("presentation")).get("climate_survival"),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def _extract_resource_changes(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    contract = _extract_turn_contract(result)
    candidates = [
        result.get("resource_changes"),
        contract.get("resource_changes"),
        _safe_dict(result.get("result")).get("resource_changes"),
        _safe_dict(_safe_dict(result.get("result")).get("turn_contract")).get("resource_changes"),
    ]
    for value in candidates:
        if isinstance(value, dict) and value:
            return value
    return {}


def _llm_called(result: Dict[str, Any]) -> bool:
    result = _safe_dict(result)
    payload = _safe_dict(
        result.get("narration_payload")
        or result.get("structured_narration")
        or result.get("narration_result")
        or _safe_dict(result.get("result")).get("narration_payload")
        or _safe_dict(result.get("result")).get("structured_narration")
    )
    return bool(
        result.get("llm_called")
        or _safe_dict(result.get("result")).get("llm_called")
        or payload.get("source") == "provider_runtime_narration"
        or _safe_dict(payload.get("provider_call_diagnostics")).get("called")
    )


def _build_row(turn_index: int, player_input: str, result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _extract_turn_contract(result)
    row = {
        "turn_index": turn_index,
        "player": player_input,
        "result": result,
        "turn_contract": contract,
        "climate_survival": _extract_climate_survival(result),
        "resource_changes": _extract_resource_changes(result),
        "llm_called": _llm_called(result),
        "raw_result_keys": sorted(str(key) for key in _safe_dict(result).keys()),
    }
    return row


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_smoke(*, turns: int, session_id: str, require_llm: bool) -> Dict[str, Any]:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    _reset_manual_session_artifacts(session_id)
    _ensure_manual_session(session_id)
    apply_turn = _get_apply_turn()

    selected_turns = list(DEFAULT_TURNS)
    while len(selected_turns) < turns:
        selected_turns.append("I wait and monitor my condition.")
    selected_turns = selected_turns[: max(1, turns)]

    raw_rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, player_input in enumerate(selected_turns, start=1):
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

    ok = bool(source_gate.get("ok")) and not errors
    if require_llm and llm_called_count <= 0:
        ok = False

    summary = {
        "format_version": "n1253_manual_survival_source_smoke_v1",
        "ok": ok,
        "session_id": session_id,
        "turns_requested": turns,
        "turns_executed": len(projected_rows),
        "llm_called_count": llm_called_count,
        "require_llm": require_llm,
        "errors": errors,
        "source_gate": source_gate,
        "source_summary": source_summary,
        "pressure_summary": {
            key: value
            for key, value in pressure_summary.items()
            if key not in {"trend_rows"}
        },
    }

    _write_json(RESULT_ROOT / "manual-survival-source-smoke-summary.json", summary)
    _write_json(RESULT_ROOT / "manual-survival-source-smoke-rows.json", projected_rows)
    _write_json(RESULT_ROOT / "manual-survival-source-smoke-source-summary.json", source_summary)
    _write_json(RESULT_ROOT / "manual-survival-source-smoke-source-gate.json", source_gate)
    _write_json(RESULT_ROOT / "manual-survival-source-smoke-pressure-summary.json", pressure_summary)
    return summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run short N125 survival source smoke against live RPG runtime/LLM.")
    parser.add_argument("--turns", type=int, default=3, help="Number of live turns to run. Default: 3.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to smoke timestamp/uuid.")
    parser.add_argument("--require-llm", action="store_true", help="Fail if no turn reports an LLM/provider call.")
    args = parser.parse_args(argv)

    session_id = args.session_id.strip() or f"manual_survival_source_smoke_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    summary = run_smoke(turns=max(1, int(args.turns or 3)), session_id=session_id, require_llm=bool(args.require_llm))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
