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
_LLM_TRUE_KEYS = {
    "called",
    "llm_called",
    "model_called",
    "provider_called",
    "provider_requested",
    "provider_attempted",
    "provider_valid",
    "used_llm",
    "used_provider",
}
_LLM_COUNT_KEYS = {
    "attempt_count",
    "completion_tokens",
    "input_tokens",
    "llm_call_count",
    "output_tokens",
    "provider_attempt_count",
    "provider_call_count",
    "raw_text_length",
    "total_tokens",
}
_LLM_TEXT_KEYS = {
    "raw_text",
    "raw_text_excerpt",
    "response_text",
    "structured_narration_text",
}
_LLM_SOURCE_MARKERS = (
    "provider_runtime_narration",
    "runtime_provider_narration",
    "central_provider",
    "llm_provider",
    "provider_call",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def _extract_narration_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    session = _safe_dict(result.get("session"))
    candidates = [
        result.get("narration_payload"),
        result.get("structured_narration"),
        result.get("narration_result"),
        result_sub.get("narration_payload"),
        result_sub.get("structured_narration"),
        result_sub.get("narration_result"),
        session.get("last_narration_payload"),
        session.get("narration_payload"),
    ]
    for value in candidates:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _value_looks_like_provider_source(value: Any) -> bool:
    text = _safe_str(value).strip().lower()
    if not text:
        return False
    if text in {"fallback", "deterministic_fallback", "none", "disabled"}:
        return False
    return any(marker in text for marker in _LLM_SOURCE_MARKERS)


def _diagnostic_provider_call_seen(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    if not payload:
        return False
    for key, value in payload.items():
        key_l = _safe_str(key).lower()
        if key_l in _LLM_TRUE_KEYS and value is True:
            return True
        if key_l in _LLM_COUNT_KEYS and _safe_int(value, 0) > 0:
            return True
        if key_l in _LLM_TEXT_KEYS and _safe_str(value).strip():
            return True
    for key in ("source", "selected_method", "method", "provider_source", "narration_source"):
        if _value_looks_like_provider_source(payload.get(key)):
            return True
    return False


def _collect_llm_evidence_paths(value: Any, *, prefix: str = "root", limit: int = 12) -> List[str]:
    """Return compact evidence paths proving a live provider/LLM call happened.

    Runtime payload shapes have changed repeatedly across N12x work.  Older
    smokes only checked a handful of top-level narration diagnostics fields,
    which made ``--require-llm`` fail even when the provider evidence had simply
    moved under result/session/runtime diagnostics.  This recursive scanner is
    intentionally evidence-only: it records positive booleans, positive counts,
    non-empty raw provider text, or explicit provider-runtime source markers.
    """

    found: List[str] = []

    def visit(node: Any, path: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            if _diagnostic_provider_call_seen(node):
                found.append(path)
                if len(found) >= limit:
                    return
            for key, child in node.items():
                key_l = _safe_str(key).lower()
                child_path = f"{path}.{key_l}"
                if key_l in _LLM_TRUE_KEYS and child is True:
                    found.append(child_path)
                elif key_l in _LLM_COUNT_KEYS and _safe_int(child, 0) > 0:
                    found.append(child_path)
                elif key_l in _LLM_TEXT_KEYS and _safe_str(child).strip():
                    found.append(child_path)
                elif key_l in {"source", "selected_method", "method", "provider_source", "narration_source"} and _value_looks_like_provider_source(child):
                    found.append(child_path)
                if len(found) >= limit:
                    return
                if isinstance(child, (dict, list)):
                    visit(child, child_path)
                    if len(found) >= limit:
                        return
        elif isinstance(node, list):
            for index, child in enumerate(node[:20]):
                if isinstance(child, (dict, list)):
                    visit(child, f"{path}[{index}]")
                    if len(found) >= limit:
                        return

    visit(value, prefix)
    deduped: List[str] = []
    seen = set()
    for item in found:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped[:limit]


def _provider_call_seen(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    diagnostics_sources = [
        payload.get("provider_call_diagnostics"),
        _safe_dict(payload.get("runtime_narration_diagnostics")).get("provider_call_diagnostics"),
        payload.get("runtime_narration_diagnostics"),
    ]
    for diagnostics_source in diagnostics_sources:
        diagnostics = _safe_dict(diagnostics_source)
        if not diagnostics:
            continue
        if _diagnostic_provider_call_seen(diagnostics):
            return True
    return bool(_collect_llm_evidence_paths(payload, prefix="narration_payload", limit=1))


def _llm_evidence_paths(result: Dict[str, Any]) -> List[str]:
    result = _safe_dict(result)
    payload = _extract_narration_payload(result)
    paths: List[str] = []
    if result.get("llm_called"):
        paths.append("result.llm_called")
    if _safe_dict(result.get("result")).get("llm_called"):
        paths.append("result.result.llm_called")
    if payload.get("source") == "provider_runtime_narration":
        paths.append("narration_payload.source")
    if _provider_call_seen(payload):
        paths.extend(_collect_llm_evidence_paths(payload, prefix="narration_payload"))
    paths.extend(_collect_llm_evidence_paths(result, prefix="result"))
    deduped: List[str] = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped[:16]


def _llm_called(result: Dict[str, Any]) -> bool:
    return bool(_llm_evidence_paths(result))


def _build_row(turn_index: int, player_input: str, result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _extract_turn_contract(result)
    llm_evidence = _llm_evidence_paths(result)
    row = {
        "turn_index": turn_index,
        "player": player_input,
        "result": result,
        "turn_contract": contract,
        "climate_survival": _extract_climate_survival(result),
        "resource_changes": _extract_resource_changes(result),
        "llm_called": bool(llm_evidence),
        "llm_evidence_paths": llm_evidence,
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
    llm_evidence_paths = [
        {"turn_index": row.get("turn_index"), "paths": row.get("llm_evidence_paths") or []}
        for row in projected_rows
        if row.get("llm_evidence_paths")
    ]

    ok = bool(source_gate.get("ok")) and not errors
    if require_llm and llm_called_count <= 0:
        ok = False

    summary = {
        "format_version": "n1253_manual_survival_source_smoke_v2",
        "ok": ok,
        "session_id": session_id,
        "turns_requested": turns,
        "turns_executed": len(projected_rows),
        "llm_called_count": llm_called_count,
        "llm_evidence_paths": llm_evidence_paths,
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
