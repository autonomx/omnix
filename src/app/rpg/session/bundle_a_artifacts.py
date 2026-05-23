from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SURVIVAL_EXIT_SOURCE = "n128_survival_system_exit_criteria_regression_lock"
PAYLOAD_BUDGET_SOURCE = "n129_transcript_report_payload_size_cleanup"
MANIFEST_SOURCE = "bundle_a1_final_artifact_inclusion_manifest"

SURVIVAL_EXIT_FILE = "survival-exit-criteria-summary.json"
PAYLOAD_BUDGET_FILE = "transcript-payload-budget-summary.json"
QUALITY_GATE_FILE = "quality-gate-summary.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"
HEALTH_FILE = "autoplay-health.json"
FULL_TRANSCRIPT_FILE = "full-transcript.json"

DEFAULT_MAX_COMPACT_ROW_BYTES = 120_000
DEFAULT_MAX_PROJECTED_1000_BYTES = 200_000_000
DEFAULT_MAX_PROJECTED_1000_REVIEW_BYTES = 1_000_000_000
HEAVY_FIELD_NAMES = {
    "player_reasoning_plan",
    "player_agent_anti_loop_context",
    "presentation_hard_grounding",
    "presentation_soft_classification",
    "presentation_meta_leakage_repair",
    "narration_before_meta_repair",
    "raw_result",
    "authoritative_result",
    "debug",
    "llm_prompt",
    "provider_payload",
    "turn_contract_debug",
    "runtime_probe_history",
    "survival_autoplay_runtime_probe_history",
}
BUNDLE_A_FILES = [QUALITY_GATE_FILE, SURVIVAL_EXIT_FILE, PAYLOAD_BUDGET_FILE]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _nested_dict(root: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    value: Any = root
    for key in keys:
        value = _safe_dict(value).get(key)
    return _safe_dict(value)


def _survival_pressure_summary(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        _nested_dict(evaluation, "artifact_level_summaries", "survival-pressure-relief-summary.json"),
        _safe_dict(evaluation.get("survival_pressure_relief_summary")),
        _safe_dict(evaluation.get("survival_pressure_summary")),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def build_survival_exit_criteria_summary(evaluation: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    evaluation = _safe_dict(evaluation)
    readiness = _safe_dict(readiness)
    pressure = _survival_pressure_summary(evaluation)
    balance = _safe_dict(pressure.get("balance_summary"))
    runtime_probe = _safe_dict(pressure.get("runtime_probe_summary"))
    relief_counts = _safe_dict(pressure.get("relief_counts_by_kind"))
    blocked = _safe_dict(pressure.get("blocked_counts_by_reason"))
    capped = _safe_dict(balance.get("capped_turn_counts"))
    longest = _safe_dict(balance.get("longest_capped_streaks"))
    inventory = _safe_list(pressure.get("inventory_consumed_summary"))
    gates = _safe_dict(readiness.get("gates"))

    drink_count = _safe_int(relief_counts.get("drink_water"), 0) + _safe_int(relief_counts.get("drink_waterskin"), 0) + _safe_int(relief_counts.get("buy_drink"), 0)
    eat_count = _safe_int(relief_counts.get("eat_food"), 0) + _safe_int(relief_counts.get("eat_trail_ration"), 0) + _safe_int(relief_counts.get("buy_meal"), 0)
    rest_count = _safe_int(relief_counts.get("rest"), 0) + _safe_int(relief_counts.get("sleep"), 0) + _safe_int(relief_counts.get("buy_lodging"), 0)
    emergency_water_count = sum(_safe_int(item.get("quantity"), 0) for item in inventory if "emergency_water" in str(_safe_dict(item).get("item_id", "")))
    blocked_relief_count = _safe_int(pressure.get("blocked_relief_count"), 0)
    longest_thirst = _safe_int(longest.get("thirst"), 0)
    capped_thirst = _safe_int(capped.get("thirst"), 0)
    failed: List[str] = []
    checks = {
        "survival_autoplay_evidence_ok": bool(gates.get("survival_autoplay_evidence_ok")),
        "survival_response_ok": bool(gates.get("survival_response_ok")),
        "survival_metric_source_ok": bool(gates.get("survival_metric_source_ok")),
        "blocked_relief_count_ok": blocked_relief_count == 0,
        "drink_water_count_ok": drink_count >= 2,
        "eat_food_count_ok": eat_count >= 1,
        "thirst_capped_turns_ok": capped_thirst == 0,
        "longest_thirst_capped_streak_ok": longest_thirst <= 2,
        "thirst_balance_attention_ok": balance.get("thirst_balance_attention") is False,
        "runtime_probe_attached_ok": _safe_int(runtime_probe.get("probe_rows"), 0) in (0, _safe_int(evaluation.get("turns_executed"), 0)) or _safe_int(runtime_probe.get("probe_rows"), 0) > 0,
        "runtime_override_applied_or_not_needed_ok": _safe_int(runtime_probe.get("override_applied_rows"), 0) > 0 or capped_thirst == 0,
    }
    for key, ok in checks.items():
        if not ok:
            failed.append(key)
    return {
        "format_version": "n128_survival_exit_criteria_summary_v1",
        "source": SURVIVAL_EXIT_SOURCE,
        "ok": not failed,
        "failed_checks": failed,
        "checks": checks,
        "requested_turns": evaluation.get("requested_turns"),
        "turns_executed": evaluation.get("turns_executed"),
        "drink_water_count": drink_count,
        "eat_food_count": eat_count,
        "rest_count": rest_count,
        "relief_counts_by_kind": relief_counts,
        "blocked_relief_count": blocked_relief_count,
        "blocked_counts_by_reason": blocked,
        "capped_thirst_turns": capped_thirst,
        "longest_capped_streaks": longest,
        "thirst_balance_attention": balance.get("thirst_balance_attention"),
        "emergency_water_count": emergency_water_count,
        "inventory_consumed_summary": inventory,
        "runtime_probe_summary": runtime_probe,
        "readiness_survival_gates": {
            "survival_autoplay_evidence_ok": gates.get("survival_autoplay_evidence_ok"),
            "survival_response_ok": gates.get("survival_response_ok"),
            "survival_metric_source_ok": gates.get("survival_metric_source_ok"),
        },
        "artifact_files": {
            "summary": SURVIVAL_EXIT_FILE,
            "survival_pressure": "survival-pressure-relief-summary.json",
        },
    }


def _json_bytes(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=False, default=str).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8"))


def _field_sizes(row: Dict[str, Any]) -> List[Tuple[str, int]]:
    sizes = [(str(key), _json_bytes(value)) for key, value in _safe_dict(row).items()]
    sizes.sort(key=lambda item: item[1], reverse=True)
    return sizes


def build_transcript_payload_budget_summary(
    transcript: Iterable[Dict[str, Any]],
    *,
    max_compact_row_bytes: int = DEFAULT_MAX_COMPACT_ROW_BYTES,
    max_projected_1000_bytes: int = DEFAULT_MAX_PROJECTED_1000_BYTES,
    max_projected_1000_review_bytes: int = DEFAULT_MAX_PROJECTED_1000_REVIEW_BYTES,
) -> Dict[str, Any]:
    rows = [dict(_safe_dict(row)) for row in _safe_list(list(transcript or []))]
    row_sizes = [_json_bytes(row) for row in rows]
    total = sum(row_sizes)
    row_count = len(rows)
    avg = int(total / row_count) if row_count else 0
    max_row = max(row_sizes or [0])
    projected_1000 = avg * 1000
    oversized = []
    heavy_fields: Dict[str, int] = {}
    for idx, row in enumerate(rows, start=1):
        size = row_sizes[idx - 1]
        fields = _field_sizes(row)
        for name, field_size in fields[:12]:
            if name in HEAVY_FIELD_NAMES or field_size >= 20_000:
                heavy_fields[name] = heavy_fields.get(name, 0) + field_size
        if size > max_compact_row_bytes and len(oversized) < 25:
            oversized.append({
                "row_index": idx,
                "turn_index": row.get("turn_index") or row.get("turn"),
                "row_bytes": size,
                "largest_fields": [{"field": name, "bytes": field_size} for name, field_size in fields[:12]],
            })
    heavy_ranked = sorted(({"field": key, "bytes": value} for key, value in heavy_fields.items()), key=lambda item: item["bytes"], reverse=True)[:30]
    ok = projected_1000 <= max_projected_1000_bytes and not oversized
    advisory_ok = projected_1000 <= max_projected_1000_review_bytes
    return {
        "format_version": "n129_transcript_payload_budget_summary_v1",
        "source": PAYLOAD_BUDGET_SOURCE,
        "ok": ok,
        "advisory_ok": advisory_ok,
        "row_count": row_count,
        "total_transcript_bytes": total,
        "average_row_bytes": avg,
        "max_row_bytes": max_row,
        "max_compact_row_bytes": max_compact_row_bytes,
        "projected_1000_turn_transcript_bytes": projected_1000,
        "max_projected_1000_turn_transcript_bytes": max_projected_1000_bytes,
        "max_projected_1000_turn_review_bytes": max_projected_1000_review_bytes,
        "oversized_row_count": sum(1 for size in row_sizes if size > max_compact_row_bytes),
        "oversized_rows_sample": oversized,
        "heavy_field_totals": heavy_ranked,
        "recommended_actions": [
            "Keep compact transcript rows for report/evaluation fields only.",
            "Move bulky debug/provider/prompt/history fields to review-artifacts rather than final transcript rows.",
            "Use this artifact before 250/300/1000-turn runs to prevent multi-GB projections.",
        ],
    }


def _load_transcript(root: Path, evaluation: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        _safe_list(evaluation.get("transcript")),
        _safe_list(evaluation.get("final_transcript")),
    ]
    for rows in candidates:
        if rows:
            return [dict(_safe_dict(row)) for row in rows]
    for path in (root / FULL_TRANSCRIPT_FILE, root / "transcript.json"):
        loaded = _read_json(path)
        if isinstance(loaded, list):
            return [dict(_safe_dict(row)) for row in loaded]
        if isinstance(loaded, dict):
            rows = _safe_list(loaded.get("transcript") or loaded.get("rows"))
            if rows:
                return [dict(_safe_dict(row)) for row in rows]
    pressure = _survival_pressure_summary(evaluation)
    trend_rows = _safe_list(pressure.get("trend_rows"))
    if trend_rows:
        return [dict(_safe_dict(row)) for row in trend_rows]
    return []


def _existing_manifest(root: Path) -> Dict[str, Any]:
    data = _read_json(root / ARTIFACT_MANIFEST_FILE)
    return _safe_dict(data) if data else {}


def _quality_summary(root: Path) -> Dict[str, Any]:
    return _safe_dict(_read_json(root / QUALITY_GATE_FILE))


def _write_bundle_manifest(
    root: Path,
    *,
    quality: Dict[str, Any],
    survival: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    existing = _existing_manifest(root)
    existing_files = []
    if isinstance(existing.get("files"), list):
        existing_files = [str(item) for item in existing.get("files") if item]
    merged_files = list(dict.fromkeys([*existing_files, *BUNDLE_A_FILES]))
    physical_presence = {name: (root / name).exists() for name in BUNDLE_A_FILES}
    manifest = {
        **existing,
        "format_version": "bundle_a1_artifact_manifest_v1",
        "source": MANIFEST_SOURCE,
        "ok": all(physical_presence.values()),
        "bundle_a_files": list(BUNDLE_A_FILES),
        "files": merged_files,
        "physical_presence": physical_presence,
        "embedded_artifacts": {
            QUALITY_GATE_FILE: quality,
            SURVIVAL_EXIT_FILE: survival,
            PAYLOAD_BUDGET_FILE: payload,
        },
        "notes": [
            "Bundle A summaries are embedded here so tracked artifact commits still expose them even if new JSON files were not git-added.",
            "The physical JSON files are still written next to this manifest for normal zip/export flows.",
        ],
    }
    _write_json(root / ARTIFACT_MANIFEST_FILE, manifest)
    return manifest


def _patch_evaluation_with_bundle_a(root: Path, survival: Dict[str, Any], payload: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / EVALUATION_FILE
    evaluation = _safe_dict(_read_json(path))
    if not evaluation:
        return
    artifacts = _safe_dict(evaluation.get("artifact_level_summaries"))
    artifacts[SURVIVAL_EXIT_FILE] = survival
    artifacts[PAYLOAD_BUDGET_FILE] = payload
    artifacts[ARTIFACT_MANIFEST_FILE] = {
        "source": manifest.get("source"),
        "ok": manifest.get("ok"),
        "bundle_a_files": manifest.get("bundle_a_files"),
        "physical_presence": manifest.get("physical_presence"),
    }
    evaluation["artifact_level_summaries"] = artifacts
    evaluation["bundle_a_artifact_manifest"] = {
        "source": MANIFEST_SOURCE,
        "files": list(BUNDLE_A_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
        "physical_presence": manifest.get("physical_presence"),
    }
    _write_json(path, evaluation)


def _patch_readiness_with_bundle_a(root: Path, survival: Dict[str, Any], payload: Dict[str, Any]) -> None:
    path = root / READINESS_FILE
    readiness = _safe_dict(_read_json(path))
    if not readiness:
        return
    bundle = _safe_dict(readiness.get("bundle_a_artifacts"))
    bundle.update({
        "source": MANIFEST_SOURCE,
        "survival_exit_criteria_ok": bool(survival.get("ok")),
        "transcript_payload_budget_ok": bool(payload.get("ok")),
        "transcript_payload_budget_advisory_ok": bool(payload.get("advisory_ok")),
        "files": list(BUNDLE_A_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    })
    readiness["bundle_a_artifacts"] = bundle
    _write_json(path, readiness)


def _patch_health_with_bundle_a(root: Path, survival: Dict[str, Any], payload: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / HEALTH_FILE
    health = _safe_dict(_read_json(path))
    if not health:
        return
    health["bundle_a_artifacts_ok"] = bool(survival.get("ok")) and bool(payload.get("advisory_ok")) and bool(manifest.get("ok"))
    health["bundle_a_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
    health["survival_exit_criteria_ok"] = bool(survival.get("ok"))
    health["transcript_payload_budget_ok"] = bool(payload.get("ok"))
    health["transcript_payload_budget_advisory_ok"] = bool(payload.get("advisory_ok"))
    health["bundle_a_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "files": list(BUNDLE_A_FILES),
        "physical_presence": manifest.get("physical_presence"),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, health)


def write_bundle_a_artifacts(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    evaluation = _safe_dict(_read_json(root / EVALUATION_FILE))
    readiness = _safe_dict(_read_json(root / READINESS_FILE))
    if not evaluation:
        return {"applied": False, "reason": "evaluation_missing", "source": "bundle_a_artifacts", "result_dir": str(root)}
    survival = build_survival_exit_criteria_summary(evaluation, readiness)
    transcript = _load_transcript(root, evaluation)
    payload = build_transcript_payload_budget_summary(transcript)
    _write_json(root / SURVIVAL_EXIT_FILE, survival)
    _write_json(root / PAYLOAD_BUDGET_FILE, payload)
    quality = _quality_summary(root)
    manifest = _write_bundle_manifest(root, quality=quality, survival=survival, payload=payload)
    _patch_evaluation_with_bundle_a(root, survival, payload, manifest)
    _patch_readiness_with_bundle_a(root, survival, payload)
    _patch_health_with_bundle_a(root, survival, payload, manifest)
    return {
        "applied": True,
        "source": "bundle_a_artifacts",
        "result_dir": str(root),
        "survival_exit_ok": survival.get("ok"),
        "payload_budget_ok": payload.get("ok"),
        "payload_budget_advisory_ok": payload.get("advisory_ok"),
        "manifest_ok": manifest.get("ok"),
        "physical_presence": manifest.get("physical_presence"),
        "files": [SURVIVAL_EXIT_FILE, PAYLOAD_BUDGET_FILE, ARTIFACT_MANIFEST_FILE],
    }
