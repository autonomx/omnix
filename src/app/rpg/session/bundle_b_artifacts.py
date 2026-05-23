from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

SOURCE_N130 = "n130_long_run_dry_run_profile_projection"
SOURCE_N131 = "n131_story_content_graph_exhaustion_forecast"
MANIFEST_SOURCE = "bundle_b_long_run_projection_manifest"

LONG_RUN_FILE = "long-run-dry-run-projection-summary.json"
CONTENT_FORECAST_FILE = "content-exhaustion-forecast-summary.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"
HEALTH_FILE = "autoplay-health.json"

BUNDLE_B_FILES = [LONG_RUN_FILE, CONTENT_FORECAST_FILE]
TARGET_PROFILES = [250, 300, 1000]
MAX_300_TURN_PROJECTED_SECONDS = 12 * 60 * 60
MAX_1000_TURN_PROJECTED_SECONDS = 36 * 60 * 60
MAX_1000_TURN_TRANSCRIPT_BYTES = 200_000_000
MAX_1000_TURN_REVIEW_BYTES = 1_000_000_000
MIN_GRAPH_DENSITY = 0.25
MIN_UNIQUE_NODE_DENSITY = 0.25


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_json(path: Path) -> Any:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _gate(evaluation: Dict[str, Any], name: str) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(evaluation.get("gates")).get(name))


def _gate_value(evaluation: Dict[str, Any], name: str) -> Dict[str, Any]:
    return _safe_dict(_gate(evaluation, name).get("value"))


def _artifact_summary(evaluation: Dict[str, Any], name: str) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(evaluation.get("artifact_level_summaries")).get(name))


def _load_or_artifact(root: Path, evaluation: Dict[str, Any], name: str) -> Dict[str, Any]:
    summary = _artifact_summary(evaluation, name)
    if summary:
        return summary
    return _safe_dict(_read_json(root / name))


def _latest_state_budget(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    compression = _gate_value(evaluation, "world_state_compression_active")
    return _safe_dict(compression.get("latest_state_budget"))


def _budget_total_bytes(state_budget: Dict[str, Any]) -> int:
    sections = _safe_dict(state_budget.get("sections"))
    return sum(_safe_int(_safe_dict(section).get("bytes"), 0) for section in sections.values())


def _budget_ok(state_budget: Dict[str, Any]) -> bool:
    if not state_budget:
        return False
    if state_budget.get("ok") is False:
        return False
    sections = _safe_dict(state_budget.get("sections"))
    return all(_safe_dict(section).get("ok") is not False for section in sections.values())


def _profile_projection(
    *,
    target_turns: int,
    base_turns: int,
    avg_turn_seconds: float,
    p95_turn_seconds: float,
    avg_row_bytes: int,
    latest_state_bytes: int,
    state_budget_ok: bool,
) -> Dict[str, Any]:
    base = max(1, base_turns)
    ratio = target_turns / base
    projected_seconds = avg_turn_seconds * target_turns
    projected_p95_seconds = p95_turn_seconds * target_turns
    projected_transcript_bytes = avg_row_bytes * target_turns
    # State compression should be bounded; keep both a bounded estimate and a
    # naive linear estimate so 1000-turn risk is visible without requiring a long run.
    bounded_state_bytes = latest_state_bytes
    linear_state_bytes = int(latest_state_bytes * ratio)
    return {
        "target_turns": target_turns,
        "base_turns": base_turns,
        "turn_ratio": ratio,
        "projected_wall_seconds_avg": round(projected_seconds, 3),
        "projected_wall_hours_avg": round(projected_seconds / 3600.0, 3),
        "projected_p95_cumulative_seconds": round(projected_p95_seconds, 3),
        "projected_transcript_bytes": projected_transcript_bytes,
        "projected_state_bytes_bounded": bounded_state_bytes,
        "projected_state_bytes_linear_risk": linear_state_bytes,
        "state_budget_ok": state_budget_ok,
    }


def build_long_run_dry_run_projection_summary(
    evaluation: Dict[str, Any],
    readiness: Dict[str, Any],
    payload_budget: Dict[str, Any],
    survival_exit: Dict[str, Any],
) -> Dict[str, Any]:
    evaluation = _safe_dict(evaluation)
    readiness = _safe_dict(readiness)
    payload_budget = _safe_dict(payload_budget)
    survival_exit = _safe_dict(survival_exit)
    perf = _gate_value(evaluation, "performance_turn_latency")
    base_turns = max(1, _safe_int(evaluation.get("turns_executed") or evaluation.get("requested_turns"), 100))
    avg_turn_seconds = _safe_float(perf.get("avg_turn_seconds"), 0.0)
    p95_turn_seconds = _safe_float(perf.get("p95_turn_seconds"), avg_turn_seconds)
    avg_row_bytes = _safe_int(payload_budget.get("average_row_bytes"), 0)
    projected_1000_payload = _safe_int(payload_budget.get("projected_1000_turn_transcript_bytes"), avg_row_bytes * 1000)
    state_budget = _latest_state_budget(evaluation)
    state_bytes = _budget_total_bytes(state_budget)
    state_ok = _budget_ok(state_budget)
    profiles = [
        _profile_projection(
            target_turns=target,
            base_turns=base_turns,
            avg_turn_seconds=avg_turn_seconds,
            p95_turn_seconds=p95_turn_seconds,
            avg_row_bytes=avg_row_bytes,
            latest_state_bytes=state_bytes,
            state_budget_ok=state_ok,
        )
        for target in TARGET_PROFILES
    ]
    profile_by_turns = {item["target_turns"]: item for item in profiles}
    checks = {
        "hundred_turn_evaluation_ok": bool(evaluation.get("ok")),
        "hundred_turn_readiness_ok": bool(readiness.get("ok")),
        "survival_exit_criteria_ok": bool(survival_exit.get("ok")),
        "payload_budget_advisory_ok": bool(payload_budget.get("advisory_ok", payload_budget.get("ok"))),
        "state_budget_ok": state_ok,
        "profile_300_wall_time_ok": _safe_float(profile_by_turns[300].get("projected_wall_seconds_avg"), 0.0) <= MAX_300_TURN_PROJECTED_SECONDS,
        "profile_1000_wall_time_advisory_ok": _safe_float(profile_by_turns[1000].get("projected_wall_seconds_avg"), 0.0) <= MAX_1000_TURN_PROJECTED_SECONDS,
        "profile_1000_transcript_budget_ok": projected_1000_payload <= MAX_1000_TURN_TRANSCRIPT_BYTES,
        "profile_1000_review_budget_ok": projected_1000_payload <= MAX_1000_TURN_REVIEW_BYTES,
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "format_version": "n130_long_run_dry_run_projection_summary_v1",
        "source": SOURCE_N130,
        "ok": not failed,
        "advisory_ok": checks["profile_1000_wall_time_advisory_ok"] and checks["profile_1000_review_budget_ok"],
        "failed_checks": failed,
        "checks": checks,
        "base_turns": base_turns,
        "target_profiles": profiles,
        "performance_source": perf,
        "payload_budget_source": {
            "average_row_bytes": avg_row_bytes,
            "projected_1000_turn_transcript_bytes": projected_1000_payload,
            "payload_budget_ok": payload_budget.get("ok"),
            "payload_budget_advisory_ok": payload_budget.get("advisory_ok"),
        },
        "state_budget_source": state_budget,
        "recommended_next_run": {
            "profile": "dry_run_300",
            "turns": 300,
            "reason": "Intermediate endurance profile before a full 1000-turn LLM run.",
        },
        "artifact_files": {"summary": LONG_RUN_FILE},
    }


def build_content_exhaustion_forecast_summary(evaluation: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    evaluation = _safe_dict(evaluation)
    readiness = _safe_dict(readiness)
    turns = max(1, _safe_int(evaluation.get("turns_executed") or readiness.get("requested_turns"), 100))
    progression_changed = _safe_int(readiness.get("progression_changed_count"), 0)
    unique_nodes = _safe_int(readiness.get("unique_progression_node_count"), 0)
    graph_count = _safe_int(readiness.get("graph_count"), 0)
    completed_graph_count = _safe_int(readiness.get("completed_graph_count"), 0)
    active_graph_count = max(0, graph_count - completed_graph_count)
    available_next_graph_count = max(0, graph_count - completed_graph_count)
    classification = str(readiness.get("classification") or "unknown")
    story_arc = _gate_value(evaluation, "story_arc_resolution_present")
    followup = _gate_value(evaluation, "followup_arc_progression_present")
    escalation = _gate_value(evaluation, "escalation_arc_progression_present")
    pressure = _gate_value(evaluation, "pressure_pacing_active")
    graph_progression_density = progression_changed / turns if turns else 0.0
    unique_node_density = unique_nodes / turns if turns else 0.0
    completed_ratio = completed_graph_count / graph_count if graph_count else 0.0
    if readiness.get("waiting_for_next_graph_pack"):
        turns_until_exhaustion = 0
    elif classification == "content_sufficient_for_requested_turns" and graph_progression_density >= MIN_GRAPH_DENSITY:
        turns_until_exhaustion = max(100, int((active_graph_count + max(1, available_next_graph_count)) * 100))
    else:
        turns_until_exhaustion = max(0, int(unique_nodes / max(0.01, graph_progression_density)))
    checks = {
        "readiness_content_classification_ok": classification == "content_sufficient_for_requested_turns",
        "graph_progression_density_ok": graph_progression_density >= MIN_GRAPH_DENSITY,
        "unique_node_density_ok": unique_node_density >= MIN_UNIQUE_NODE_DENSITY,
        "waiting_for_next_graph_pack_ok": not bool(readiness.get("waiting_for_next_graph_pack")),
        "campaign_graphs_not_fully_exhausted_ok": not bool(readiness.get("campaign_graphs_complete")),
        "available_next_graph_count_ok": available_next_graph_count >= 1,
        "story_arc_resolution_present": bool(_gate(evaluation, "story_arc_resolution_present").get("ok")),
        "followup_arc_progression_present": bool(_gate(evaluation, "followup_arc_progression_present").get("ok")),
        "escalation_arc_progression_present": bool(_gate(evaluation, "escalation_arc_progression_present").get("ok")),
        "pressure_pacing_active": bool(_gate(evaluation, "pressure_pacing_active").get("ok")),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "format_version": "n131_content_exhaustion_forecast_summary_v1",
        "source": SOURCE_N131,
        "ok": not failed,
        "advisory_ok": checks["readiness_content_classification_ok"] and checks["graph_progression_density_ok"],
        "failed_checks": failed,
        "checks": checks,
        "requested_turns": readiness.get("requested_turns"),
        "turns_executed": turns,
        "classification": classification,
        "graph_count": graph_count,
        "completed_graph_count": completed_graph_count,
        "active_graph_count": active_graph_count,
        "available_next_graph_count": available_next_graph_count,
        "campaign_graphs_complete": bool(readiness.get("campaign_graphs_complete")),
        "waiting_for_next_graph_pack": bool(readiness.get("waiting_for_next_graph_pack")),
        "progression_changed_count": progression_changed,
        "unique_progression_node_count": unique_nodes,
        "graph_progression_density": graph_progression_density,
        "unique_node_density": unique_node_density,
        "completed_graph_ratio": completed_ratio,
        "turns_until_content_exhaustion_estimate": turns_until_exhaustion,
        "story_arc_resolution": story_arc,
        "followup_arc_progression": followup,
        "escalation_arc_progression": escalation,
        "pressure_pacing": pressure,
        "recommended_next_actions": [
            "Run a 250/300-turn dry profile before a full 1000-turn run.",
            "If available_next_graph_count drops to zero, add graph packs or explicit waiting-for-next-graph handling.",
            "Track unique node density to catch repeated graph-content reuse before it becomes a loop."
        ],
        "artifact_files": {"summary": CONTENT_FORECAST_FILE},
    }


def _existing_manifest(root: Path) -> Dict[str, Any]:
    return _safe_dict(_read_json(root / ARTIFACT_MANIFEST_FILE))


def _write_manifest(root: Path, long_run: Dict[str, Any], content: Dict[str, Any]) -> Dict[str, Any]:
    existing = _existing_manifest(root)
    existing_files = [str(item) for item in _safe_list(existing.get("files")) if item]
    files = list(dict.fromkeys([*existing_files, *BUNDLE_B_FILES]))
    physical_presence = {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in BUNDLE_B_FILES}
    embedded = _safe_dict(existing.get("embedded_artifacts"))
    embedded[LONG_RUN_FILE] = long_run
    embedded[CONTENT_FORECAST_FILE] = content
    manifest = {
        **existing,
        "source": MANIFEST_SOURCE,
        "bundle_b_files": list(BUNDLE_B_FILES),
        "files": files,
        "bundle_b_physical_presence": physical_presence,
        "embedded_artifacts": embedded,
    }
    if "format_version" not in manifest:
        manifest["format_version"] = "bundle_b_artifact_manifest_v1"
    manifest["ok"] = bool(manifest.get("ok", True)) and all(physical_presence.values())
    _write_json(root / ARTIFACT_MANIFEST_FILE, manifest)
    return manifest


def _patch_evaluation(root: Path, long_run: Dict[str, Any], content: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / EVALUATION_FILE
    evaluation = _safe_dict(_read_json(path))
    if not evaluation:
        return
    summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
    summaries[LONG_RUN_FILE] = long_run
    summaries[CONTENT_FORECAST_FILE] = content
    summaries[ARTIFACT_MANIFEST_FILE] = {
        "source": manifest.get("source"),
        "ok": manifest.get("ok"),
        "bundle_b_files": manifest.get("bundle_b_files"),
        "bundle_b_physical_presence": manifest.get("bundle_b_physical_presence"),
    }
    evaluation["artifact_level_summaries"] = summaries
    evaluation["bundle_b_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "long_run_projection_ok": long_run.get("ok"),
        "content_exhaustion_forecast_ok": content.get("ok"),
        "files": list(BUNDLE_B_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, evaluation)


def _patch_readiness(root: Path, long_run: Dict[str, Any], content: Dict[str, Any]) -> None:
    path = root / READINESS_FILE
    readiness = _safe_dict(_read_json(path))
    if not readiness:
        return
    readiness["bundle_b_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "long_run_projection_ok": bool(long_run.get("ok")),
        "long_run_projection_advisory_ok": bool(long_run.get("advisory_ok")),
        "content_exhaustion_forecast_ok": bool(content.get("ok")),
        "content_exhaustion_forecast_advisory_ok": bool(content.get("advisory_ok")),
        "recommended_next_run": _safe_dict(long_run.get("recommended_next_run")),
        "turns_until_content_exhaustion_estimate": content.get("turns_until_content_exhaustion_estimate"),
        "files": list(BUNDLE_B_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, readiness)


def _patch_health(root: Path, long_run: Dict[str, Any], content: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / HEALTH_FILE
    health = _safe_dict(_read_json(path))
    if not health:
        return
    health["bundle_b_artifacts_ok"] = bool(long_run.get("ok")) and bool(content.get("ok")) and bool(manifest.get("ok", True))
    health["long_run_projection_ok"] = bool(long_run.get("ok"))
    health["long_run_projection_advisory_ok"] = bool(long_run.get("advisory_ok"))
    health["content_exhaustion_forecast_ok"] = bool(content.get("ok"))
    health["content_exhaustion_forecast_advisory_ok"] = bool(content.get("advisory_ok"))
    health["bundle_b_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
    health["bundle_b_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "files": list(BUNDLE_B_FILES),
        "physical_presence": manifest.get("bundle_b_physical_presence"),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, health)


def write_bundle_b_artifacts(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    evaluation = _safe_dict(_read_json(root / EVALUATION_FILE))
    readiness = _safe_dict(_read_json(root / READINESS_FILE))
    if not evaluation:
        return {"applied": False, "reason": "evaluation_missing", "source": MANIFEST_SOURCE, "result_dir": str(root)}
    payload = _load_or_artifact(root, evaluation, "transcript-payload-budget-summary.json")
    survival = _load_or_artifact(root, evaluation, "survival-exit-criteria-summary.json")
    long_run = build_long_run_dry_run_projection_summary(evaluation, readiness, payload, survival)
    content = build_content_exhaustion_forecast_summary(evaluation, readiness)
    _write_json(root / LONG_RUN_FILE, long_run)
    _write_json(root / CONTENT_FORECAST_FILE, content)
    manifest = _write_manifest(root, long_run, content)
    _patch_evaluation(root, long_run, content, manifest)
    _patch_readiness(root, long_run, content)
    _patch_health(root, long_run, content, manifest)
    return {
        "applied": True,
        "source": MANIFEST_SOURCE,
        "result_dir": str(root),
        "long_run_projection_ok": long_run.get("ok"),
        "content_exhaustion_forecast_ok": content.get("ok"),
        "manifest_ok": manifest.get("ok"),
        "files": list(BUNDLE_B_FILES),
    }
