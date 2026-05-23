from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SOURCE_N132 = "n132_npc_agency_schedule_consequence_depth"
SOURCE_N133 = "n133_economy_resource_pressure_integration_v2"
MANIFEST_SOURCE = "bundle_c_npc_economy_artifact_manifest"

NPC_AGENCY_FILE = "npc-agency-schedule-summary.json"
ECONOMY_PRESSURE_FILE = "economy-resource-pressure-summary.json"
ARTIFACT_MANIFEST_FILE = "artifact-manifest.json"
EVALUATION_FILE = "hundred-turn-evaluation.json"
READINESS_FILE = "hundred-turn-readiness-summary.json"
HEALTH_FILE = "autoplay-health.json"
BUNDLE_C_FILES = [NPC_AGENCY_FILE, ECONOMY_PRESSURE_FILE]


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


def build_npc_agency_schedule_summary(evaluation: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    value = _gate_value(evaluation, "npc_agency_present")
    event_count = _safe_int(value.get("event_count"), 0)
    direct_graph_agency_count = _safe_int(value.get("direct_graph_agency_count"), 0)
    npc_count = _safe_int(value.get("npc_count"), 0)
    schedule_event_count = _safe_int(value.get("schedule_event_count"), 0)
    agency_event_count = _safe_int(value.get("agency_event_count"), 0)
    memory_event_count = _safe_int(value.get("memory_event_count"), 0)
    checks = {
        "npc_agency_gate_ok": bool(_gate(evaluation, "npc_agency_present").get("ok")),
        "npc_count_ok": npc_count >= 1,
        "schedule_events_ok": schedule_event_count >= 1,
        "memory_or_agency_events_ok": (memory_event_count + agency_event_count + direct_graph_agency_count) >= 1,
        "bounded_compression_ok": bool(_gate(evaluation, "world_state_compression_active").get("ok")),
        "readiness_ok": bool(_safe_dict(readiness).get("ok")),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "format_version": "n132_npc_agency_schedule_summary_v1",
        "source": SOURCE_N132,
        "ok": not failed,
        "advisory_ok": checks["npc_agency_gate_ok"] and checks["npc_count_ok"],
        "failed_checks": failed,
        "checks": checks,
        "event_count": event_count,
        "direct_graph_agency_count": direct_graph_agency_count,
        "npc_count": npc_count,
        "schedule_event_count": schedule_event_count,
        "agency_event_count": agency_event_count,
        "memory_event_count": memory_event_count,
        "presence_gating_note": "Current Bundle C locks evidence that NPC schedule/agency exists; next gameplay pass can make presence-gated dialogue stricter.",
        "recommended_next_actions": [
            "Project NPC Agency Timeline into the HTML report.",
            "Track named NPC goal changes and location/presence changes in future long-run runs.",
            "Use schedule_event_count and memory_event_count as regression evidence for long-run NPC agency."
        ],
        "artifact_files": {"summary": NPC_AGENCY_FILE},
    }


def build_economy_resource_pressure_summary(evaluation: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Any]:
    value = _gate_value(evaluation, "economy_pressure_present")
    world_signal = _gate_value(evaluation, "world_signal_summary_present")
    event_count = _safe_int(value.get("event_count"), 0)
    paid_count = _safe_int(value.get("paid_count"), 0)
    unpaid_count = _safe_int(value.get("unpaid_count"), 0)
    warning_count = _safe_int(value.get("warning_count"), 0)
    total_spent = _safe_dict(value.get("total_spent"))
    ending_currency = _safe_dict(value.get("ending_currency"))
    economy_signal_count = _safe_int(_safe_dict(world_signal.get("by_kind")).get("economy_pressure"), 0)
    checks = {
        "economy_pressure_gate_ok": bool(_gate(evaluation, "economy_pressure_present").get("ok")),
        "paid_events_ok": paid_count >= 1,
        "unpaid_events_bounded_ok": unpaid_count <= max(1, paid_count),
        "spend_recorded_ok": bool(total_spent),
        "ending_currency_recorded_ok": bool(ending_currency),
        "economy_world_signal_ok": economy_signal_count >= 1,
        "readiness_ok": bool(_safe_dict(readiness).get("ok")),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "format_version": "n133_economy_resource_pressure_summary_v1",
        "source": SOURCE_N133,
        "ok": not failed,
        "advisory_ok": checks["economy_pressure_gate_ok"] and checks["paid_events_ok"],
        "failed_checks": failed,
        "checks": checks,
        "event_count": event_count,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "warning_count": warning_count,
        "ending_currency": ending_currency,
        "total_spent": total_spent,
        "economy_world_signal_count": economy_signal_count,
        "service_priority_note": "Current Bundle C locks economy pressure evidence; future gameplay pass should prefer merchant food/drink/lodging before emergency fallback.",
        "recommended_next_actions": [
            "Project Economy / Resource Pressure into the HTML report.",
            "Track merchant-backed food/drink/lodging usage versus emergency fallback.",
            "Add scarcity/restock/price-pressure evidence before 250/300-turn dry run if economy pressure becomes too static."
        ],
        "artifact_files": {"summary": ECONOMY_PRESSURE_FILE},
    }


def _existing_manifest(root: Path) -> Dict[str, Any]:
    return _safe_dict(_read_json(root / ARTIFACT_MANIFEST_FILE))


def _write_manifest(root: Path, npc: Dict[str, Any], economy: Dict[str, Any]) -> Dict[str, Any]:
    existing = _existing_manifest(root)
    files = list(dict.fromkeys([*[str(item) for item in _safe_list(existing.get("files")) if item], *BUNDLE_C_FILES]))
    physical = {name: (root / name).exists() and (root / name).stat().st_size > 2 for name in BUNDLE_C_FILES}
    embedded = _safe_dict(existing.get("embedded_artifacts"))
    embedded[NPC_AGENCY_FILE] = npc
    embedded[ECONOMY_PRESSURE_FILE] = economy
    manifest = {
        **existing,
        "source": MANIFEST_SOURCE,
        "bundle_c_files": list(BUNDLE_C_FILES),
        "files": files,
        "bundle_c_physical_presence": physical,
        "embedded_artifacts": embedded,
    }
    if "format_version" not in manifest:
        manifest["format_version"] = "bundle_c_artifact_manifest_v1"
    manifest["ok"] = bool(manifest.get("ok", True)) and all(physical.values())
    _write_json(root / ARTIFACT_MANIFEST_FILE, manifest)
    return manifest


def _patch_evaluation(root: Path, npc: Dict[str, Any], economy: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / EVALUATION_FILE
    evaluation = _safe_dict(_read_json(path))
    if not evaluation:
        return
    summaries = _safe_dict(evaluation.get("artifact_level_summaries"))
    summaries[NPC_AGENCY_FILE] = npc
    summaries[ECONOMY_PRESSURE_FILE] = economy
    summaries[ARTIFACT_MANIFEST_FILE] = {
        "source": manifest.get("source"),
        "ok": manifest.get("ok"),
        "bundle_c_files": manifest.get("bundle_c_files"),
        "bundle_c_physical_presence": manifest.get("bundle_c_physical_presence"),
    }
    evaluation["artifact_level_summaries"] = summaries
    evaluation["bundle_c_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "npc_agency_schedule_ok": npc.get("ok"),
        "economy_resource_pressure_ok": economy.get("ok"),
        "files": list(BUNDLE_C_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, evaluation)


def _patch_readiness(root: Path, npc: Dict[str, Any], economy: Dict[str, Any]) -> None:
    path = root / READINESS_FILE
    readiness = _safe_dict(_read_json(path))
    if not readiness:
        return
    readiness["bundle_c_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "npc_agency_schedule_ok": bool(npc.get("ok")),
        "npc_agency_schedule_advisory_ok": bool(npc.get("advisory_ok")),
        "economy_resource_pressure_ok": bool(economy.get("ok")),
        "economy_resource_pressure_advisory_ok": bool(economy.get("advisory_ok")),
        "files": list(BUNDLE_C_FILES),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, readiness)


def _patch_health(root: Path, npc: Dict[str, Any], economy: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    path = root / HEALTH_FILE
    health = _safe_dict(_read_json(path))
    if not health:
        return
    health["bundle_c_artifacts_ok"] = bool(npc.get("ok")) and bool(economy.get("ok")) and bool(manifest.get("ok", True))
    health["npc_agency_schedule_ok"] = bool(npc.get("ok"))
    health["npc_agency_schedule_advisory_ok"] = bool(npc.get("advisory_ok"))
    health["economy_resource_pressure_ok"] = bool(economy.get("ok"))
    health["economy_resource_pressure_advisory_ok"] = bool(economy.get("advisory_ok"))
    health["bundle_c_artifact_manifest_path"] = ARTIFACT_MANIFEST_FILE
    health["bundle_c_artifacts"] = {
        "source": MANIFEST_SOURCE,
        "files": list(BUNDLE_C_FILES),
        "physical_presence": manifest.get("bundle_c_physical_presence"),
        "manifest_file": ARTIFACT_MANIFEST_FILE,
    }
    _write_json(path, health)


def write_bundle_c_artifacts(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir)
    evaluation = _safe_dict(_read_json(root / EVALUATION_FILE))
    readiness = _safe_dict(_read_json(root / READINESS_FILE))
    if not evaluation:
        return {"applied": False, "reason": "evaluation_missing", "source": MANIFEST_SOURCE, "result_dir": str(root)}
    npc = build_npc_agency_schedule_summary(evaluation, readiness)
    economy = build_economy_resource_pressure_summary(evaluation, readiness)
    _write_json(root / NPC_AGENCY_FILE, npc)
    _write_json(root / ECONOMY_PRESSURE_FILE, economy)
    manifest = _write_manifest(root, npc, economy)
    _patch_evaluation(root, npc, economy, manifest)
    _patch_readiness(root, npc, economy)
    _patch_health(root, npc, economy, manifest)
    return {
        "applied": True,
        "source": MANIFEST_SOURCE,
        "result_dir": str(root),
        "npc_agency_schedule_ok": npc.get("ok"),
        "economy_resource_pressure_ok": economy.get("ok"),
        "manifest_ok": manifest.get("ok"),
        "files": list(BUNDLE_C_FILES),
    }
