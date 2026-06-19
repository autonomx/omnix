"""Post-run item coverage artifacts for RPG autoplay campaigns.

The 100-turn harness writes a mixture of summary, transcript, and probe JSON
artifacts.  This module extracts the latest RPG state that contains item
mechanics, attaches the deterministic item autoplay report payload, and appends a
compact item artifact bundle into the autoplay ZIP.  It is post-run only and does
not mutate simulation truth.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

from app.rpg.session.item_autoplay_adapter import attach_item_autoplay_report, extract_item_autoplay_state
from app.rpg.session.item_endurance_scenarios import (
    build_item_endurance_plan,
    summarize_item_endurance_progress,
)

ITEM_AUTOPLAY_REPORT_HOOK_SOURCE = "autoplay_item_report_hook_v1"
ITEM_AUTOPLAY_REPORT_JSON_NAME = "item-autoplay-report.json"
ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME = "item-autoplay-report-rows.json"
ITEM_AUTOPLAY_ENDURANCE_JSON_NAME = "item-endurance-progress.json"
ITEM_AUTOPLAY_MANIFEST_JSON_NAME = "item-autoplay-manifest.json"
_MAX_JSON_FILES = 80
_MAX_ZIP_JSON_MEMBERS = 80


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_values_from_payload(value: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        values.append(value)
        for key in (
            "summary",
            "state",
            "game",
            "session",
            "result",
            "turn_result",
            "final_state",
            "simulation_state",
        ):
            nested = value.get(key)
            if nested is not None:
                values.extend(_candidate_values_from_payload(nested))
        for key in ("transcript_rows", "rows", "turns", "results", "events"):
            nested_rows = value.get(key)
            if isinstance(nested_rows, list):
                for item in nested_rows[-25:]:
                    values.extend(_candidate_values_from_payload(item))
    elif isinstance(value, list):
        for item in value[-25:]:
            values.extend(_candidate_values_from_payload(item))
    return values


def _looks_like_item_state(value: Any) -> bool:
    state = extract_item_autoplay_state(value)
    if state:
        return True
    raw = _safe_dict(value)
    if not raw:
        return False
    mechanics = _safe_dict(raw.get("mechanics"))
    player = _safe_dict(raw.get("player"))
    if mechanics and any("item" in str(key).lower() for key in mechanics.keys()):
        return True
    inventory = player.get("inventory")
    if isinstance(inventory, list) and inventory:
        return True
    if _safe_list(_safe_dict(raw.get("inventory_state")).get("items")):
        return True
    runtime_inventory = _safe_dict(_safe_dict(raw.get("player_state")).get("inventory"))
    if _safe_list(runtime_inventory.get("items")):
        return True
    return bool(raw.get("crafting") or raw.get("item_market") or raw.get("equipment"))


def _score_candidate_state(state: dict[str, Any]) -> int:
    normalized = extract_item_autoplay_state(state) or state
    mechanics = _safe_dict(normalized.get("mechanics"))
    player = _safe_dict(normalized.get("player"))
    score = 0
    score += len(_safe_list(player.get("inventory"))) * 2
    score += len(_safe_dict(normalized.get("crafting")).get("known_recipes") or [])
    for key, value in mechanics.items():
        if "item" in str(key).lower():
            score += 5 + len(_safe_list(value))
    if normalized.get("current_turn") or normalized.get("turn_count"):
        score += 3
    if _safe_list(_safe_dict(state.get("inventory_state")).get("items")):
        score += 4
    if state.get("progression_completed_node_count"):
        score += 1
    return score


def _extract_candidate_states(value: Any) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    seen: set[int] = set()
    for candidate in _candidate_values_from_payload(value):
        if not isinstance(candidate, dict):
            continue
        candidate_id = id(candidate)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        normalized = extract_item_autoplay_state(candidate)
        if normalized:
            states.append(normalized)
        elif _looks_like_item_state(candidate):
            states.append(candidate)
    states.sort(key=_score_candidate_state, reverse=True)
    return states


def _load_candidate_states_from_file(path: Path) -> list[dict[str, Any]]:
    try:
        return _extract_candidate_states(_load_json_file(path))
    except Exception:
        return []


def _load_candidate_states_from_zip(zip_path: Path) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            json_names = [name for name in archive.namelist() if name.lower().endswith(".json")]
            for name in json_names[:_MAX_ZIP_JSON_MEMBERS]:
                if name.endswith(ITEM_AUTOPLAY_REPORT_JSON_NAME) or name.endswith(ITEM_AUTOPLAY_ENDURANCE_JSON_NAME):
                    continue
                try:
                    states.extend(_extract_candidate_states(_load_json_bytes(archive.read(name))))
                except Exception:
                    continue
    except Exception:
        return []
    states.sort(key=_score_candidate_state)
    return states


def collect_item_autoplay_states(output_dir: str | Path, *, zip_paths: Iterable[str | Path] = ()) -> list[dict[str, Any]]:
    """Collect likely item-capable RPG states from autoplay artifacts."""

    output = Path(output_dir)
    states: list[dict[str, Any]] = []
    if output.exists():
        json_files = sorted(
            [path for path in output.rglob("*.json") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:_MAX_JSON_FILES]
        for path in json_files:
            if path.name in {ITEM_AUTOPLAY_REPORT_JSON_NAME, ITEM_AUTOPLAY_ENDURANCE_JSON_NAME, ITEM_AUTOPLAY_MANIFEST_JSON_NAME}:
                continue
            states.extend(_load_candidate_states_from_file(path))
    for raw_path in zip_paths:
        path = Path(raw_path)
        if path.exists():
            states.extend(_load_candidate_states_from_zip(path))
    states.sort(key=_score_candidate_state, reverse=True)
    return states


def _write_json(path: Path, payload: Any) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(data, encoding="utf-8")
    return {"ok": True, "path": str(path), "size_bytes": len(data.encode("utf-8"))}


def _append_json_to_zip(zip_path: Path, *, prefix: str, name: str, payload: Any) -> dict[str, Any]:
    if not zip_path.exists():
        return {"ok": False, "reason": "zip_not_found", "zip_path": str(zip_path)}
    member = f"{prefix.strip().strip('/')}/{name}" if prefix else name
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    try:
        with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, data)
    except Exception as exc:
        return {"ok": False, "reason": "zip_append_failed", "error": repr(exc), "zip_path": str(zip_path)}
    return {"ok": True, "zip_path": str(zip_path), "member": member, "size_bytes": len(data)}


def _item_trace_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    mechanics = _safe_dict(state.get("mechanics"))
    traces: list[dict[str, Any]] = []
    for value in mechanics.values():
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    traces.append(entry)
    return traces[-500:]


def build_item_autoplay_artifacts(state: dict[str, Any], *, total_turns: int = 100) -> dict[str, Any]:
    """Build the compact item artifacts for a final autoplay state."""

    attached = attach_item_autoplay_report({"state": state}, objective_limit=12, scenario_limit=12, recent_trace_limit=12)
    report = _safe_dict(attached.get("item_autoplay_report"))
    rows = _safe_list(attached.get("item_autoplay_report_rows"))
    plan = build_item_endurance_plan(total_turns=total_turns)
    progress = summarize_item_endurance_progress(plan, _item_trace_events(state))
    return {
        "ok": bool(report.get("ok")),
        "report": report,
        "rows": rows,
        "endurance_plan": plan,
        "endurance_progress": progress,
        "source": ITEM_AUTOPLAY_REPORT_HOOK_SOURCE,
    }


def run_autoplay_item_report_hook(
    output_dir: str | Path,
    *,
    zip_paths: Iterable[str | Path] = (),
    total_turns: int = 100,
    prefix: str = "item",
) -> dict[str, Any]:
    """Write and append item coverage artifacts for a completed autoplay run."""

    output = Path(output_dir)
    zip_path_list = [Path(path) for path in zip_paths if path]
    states = collect_item_autoplay_states(output, zip_paths=zip_path_list)
    if not states:
        return {
            "ok": False,
            "reason": "item_autoplay_state_not_found",
            "results_dir": str(output),
            "source": ITEM_AUTOPLAY_REPORT_HOOK_SOURCE,
        }
    artifacts = build_item_autoplay_artifacts(states[0], total_turns=total_turns)
    report_write = _write_json(output / ITEM_AUTOPLAY_REPORT_JSON_NAME, artifacts["report"])
    rows_write = _write_json(output / ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME, artifacts["rows"])
    endurance_write = _write_json(output / ITEM_AUTOPLAY_ENDURANCE_JSON_NAME, artifacts["endurance_progress"])
    manifest = {
        "ok": True,
        "results_dir": str(output),
        "state_candidates_observed": len(states),
        "report": report_write,
        "rows": rows_write,
        "endurance": endurance_write,
        "source": ITEM_AUTOPLAY_REPORT_HOOK_SOURCE,
    }
    manifest_write = _write_json(output / ITEM_AUTOPLAY_MANIFEST_JSON_NAME, manifest)
    zip_results: list[dict[str, Any]] = []
    for zip_path in zip_path_list:
        zip_results.append(_append_json_to_zip(zip_path, prefix=prefix, name=ITEM_AUTOPLAY_REPORT_JSON_NAME, payload=artifacts["report"]))
        zip_results.append(_append_json_to_zip(zip_path, prefix=prefix, name=ITEM_AUTOPLAY_REPORT_ROWS_JSON_NAME, payload=artifacts["rows"]))
        zip_results.append(_append_json_to_zip(zip_path, prefix=prefix, name=ITEM_AUTOPLAY_ENDURANCE_JSON_NAME, payload=artifacts["endurance_progress"]))
        zip_results.append(_append_json_to_zip(zip_path, prefix=prefix, name=ITEM_AUTOPLAY_MANIFEST_JSON_NAME, payload=manifest))
    return {
        "ok": True,
        "results_dir": str(output),
        "state_candidates_observed": len(states),
        "coverage_score": _safe_dict(artifacts["report"].get("summary")).get("coverage_score"),
        "endurance_ok": _safe_dict(artifacts["endurance_progress"]).get("ok"),
        "report_write": report_write,
        "rows_write": rows_write,
        "endurance_write": endurance_write,
        "manifest_write": manifest_write,
        "zip_results": zip_results,
        "source": ITEM_AUTOPLAY_REPORT_HOOK_SOURCE,
    }
