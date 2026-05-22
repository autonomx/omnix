from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.rpg.session.survival_metrics import (
    build_survival_metric_source_gate,
    build_survival_metric_source_summary,
    build_survival_pressure_relief_summary,
    survival_values,
)
from app.rpg.session.survival_transcript_projector import persist_survival_evidence_into_transcript_rows
from tests.rpg.manual.live_survival_seed import seed_live_survival_session
from tests.rpg.manual.turn_execution import _get_apply_turn
from tests.rpg.manual_survival_source_smoke import _build_row, _safe_dict

RESULT_ROOT = Path("resources/data/test-results/manual-survival-live-seed-smoke")
TURNS = [
    "I wait and listen while checking my hunger, thirst, and fatigue.",
    "I drink my waterskin.",
]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _first_min_need(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    values = survival_values(rows[0])
    return min(_safe_int(values.get("hunger")), _safe_int(values.get("thirst")), _safe_int(values.get("fatigue")))


def run_smoke(*, session_id: str, require_llm: bool) -> Dict[str, Any]:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    seed_result = seed_live_survival_session(session_id)
    apply_turn = _get_apply_turn()
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, text in enumerate(TURNS, start=1):
        try:
            result = apply_turn(session_id=session_id, player_input=text)
            rows.append(_build_row(index, text, _safe_dict(result)))
        except Exception as exc:
            errors.append(f"turn_{index}:{type(exc).__name__}:{exc}")
            break

    rows = persist_survival_evidence_into_transcript_rows(rows)
    source_summary = build_survival_metric_source_summary(rows)
    source_gate = build_survival_metric_source_gate(source_summary)
    pressure_summary = build_survival_pressure_relief_summary(rows)
    llm_called_count = sum(1 for row in rows if row.get("llm_called"))
    validation_failures: List[str] = []
    if _first_min_need(rows) < 50:
        validation_failures.append("seed_pressure_not_visible")
    if not source_gate.get("ok"):
        validation_failures.append("source_gate_failed")
    if require_llm and llm_called_count <= 0:
        validation_failures.append("llm_not_detected")

    summary = {
        "format_version": "n1262_manual_survival_live_seed_smoke_v1",
        "ok": not errors and not validation_failures,
        "session_id": session_id,
        "turns_executed": len(rows),
        "turns_requested": len(TURNS),
        "require_llm": require_llm,
        "llm_called_count": llm_called_count,
        "errors": errors,
        "validation_failures": validation_failures,
        "first_min_need": _first_min_need(rows),
        "seed_result": seed_result,
        "source_gate": source_gate,
        "source_summary": source_summary,
        "pressure_summary": {key: value for key, value in pressure_summary.items() if key != "trend_rows"},
    }
    _write_json(RESULT_ROOT / "manual-survival-live-seed-smoke-summary.json", summary)
    _write_json(RESULT_ROOT / "manual-survival-live-seed-smoke-rows.json", rows)
    _write_json(RESULT_ROOT / "manual-survival-live-seed-smoke-source-summary.json", source_summary)
    _write_json(RESULT_ROOT / "manual-survival-live-seed-smoke-source-gate.json", source_gate)
    _write_json(RESULT_ROOT / "manual-survival-live-seed-smoke-pressure-summary.json", pressure_summary)
    return summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run N126.2 live survival seed smoke.")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--require-llm", action="store_true")
    args = parser.parse_args(argv)
    session_id = args.session_id.strip() or f"manual_survival_live_seed_smoke_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    summary = run_smoke(session_id=session_id, require_llm=bool(args.require_llm))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
