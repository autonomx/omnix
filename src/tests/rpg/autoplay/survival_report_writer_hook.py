"""Bundle BI — direct autoplay survival report writer hook.

The named autoplay fragments are combined dynamically by
``autoplay_llm_campaign.py``.  Rather than patching an opaque fragment, this hook
runs after the stable wrapper's ``main()`` returns and enriches the generated
artifact directory/ZIP with post-run report artifacts.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.rpg.autoplay_report_size_guard import cap_oversized_autoplay_reports
from tests.rpg.autoplay.live_performance_bridge import append_live_performance_bridge_row
from tests.rpg.autoplay.performance_artifacts import (
    PERFORMANCE_SUMMARY_HTML_NAME,
    PERFORMANCE_SUMMARY_JSON_NAME,
    append_autoplay_performance_artifacts_to_zip,
    attach_autoplay_performance_manifest,
    write_autoplay_performance_artifacts,
)
from tests.rpg.autoplay.result_path_diagnostics import RUNTIME_TURN_RESULTS_NAME, write_result_path_diagnostics
from tests.rpg.autoplay.runtime_turn_result_capture_hook import backfill_runtime_turn_results_from_console_log
from tests.rpg.autoplay.survival_report_artifacts import (
    SURVIVAL_METRICS_HTML_NAME,
    SURVIVAL_METRICS_JSON_NAME,
    append_survival_report_artifacts_to_zip,
    attach_survival_artifact_manifest,
    write_survival_report_artifacts,
)

SURVIVAL_WRITER_HOOK_SOURCE = "autoplay_survival_report_writer_hook"
_MAX_JSON_FILES = 80
_MAX_ZIP_JSON_MEMBERS = 80
_MAX_ROWS = 5000


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _repo_root_from_script(script_path: str | Path) -> Path:
    path = Path(script_path).resolve()
    for parent in [path.parent, *path.parents]:
        if (parent / "src").exists() and (parent / "resources").exists():
            return parent
    try:
        return path.parents[3]
    except IndexError:
        return path.parent


def default_autoplay_results_dir(script_path: str | Path) -> Path:
    return _repo_root_from_script(script_path) / "resources" / "data" / "test-results"


def _load_json_file(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def load_live_performance_summary(output_dir: str | Path, *, zip_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load the live harness performance summary for advisory bridging."""
    output_dir = Path(output_dir)
    candidates = [
        output_dir / "autoplay-performance.json",
        output_dir / "autoplay-campaign-results-unzipped" / "autoplay-performance.json",
    ]
    for path in candidates:
        payload = _load_json_file(path)
        if payload:
            return payload
    if zip_path and Path(zip_path).exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in ("autoplay-performance.json", "autoplay-campaign-results-unzipped/autoplay-performance.json"):
                    if name in zf.namelist():
                        value = json.loads(zf.read(name).decode("utf-8"))
                        if isinstance(value, dict):
                            return value
        except Exception:
            return {}
    return {}


def load_runtime_turn_result_rows(output_dir: str | Path) -> List[Dict[str, Any]]:
    payload = _load_json_file(Path(output_dir) / RUNTIME_TURN_RESULTS_NAME)
    rows: List[Dict[str, Any]] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        rows.append(
            {
                "turn_index": event.get("turn_index", -1),
                "performance": {
                    "result_keys": list(event.get("result_keys") or []),
                    "traces": {
                        "result_keys": list(event.get("result_keys") or []),
                        "emitted_line": _safe_str(event.get("line")),
                    },
                },
                "source": "runtime_turn_result_capture_hook_bridge",
            }
        )
    return rows


def _has_survival_evidence(row: Mapping[str, Any]) -> bool:
    row = _safe_dict(row)
    if not row:
        return False
    evidence_keys = {
        "survival",
        "survival_pressure",
        "survival_action_context",
        "survival_result",
        "survival_tick_result",
        "autoplay_survival_pressure",
    }
    if any(key in row for key in evidence_keys):
        return True
    for nested_key in ("turn_contract", "result", "resolved_result", "interaction_result", "general_interaction_result"):
        nested = _safe_dict(row.get(nested_key))
        if nested and any(key in nested for key in evidence_keys):
            return True
    return False


def _extract_rows_from_value(value: Any, rows: List[Dict[str, Any]]) -> None:
    if len(rows) >= _MAX_ROWS:
        return
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            for item in value:
                if len(rows) >= _MAX_ROWS:
                    return
                item = _safe_dict(item)
                if _has_survival_evidence(item) or any(k in item for k in ("turn", "turn_index", "tick", "turn_contract", "result", "turn_result", "performance", "timing")):
                    rows.append(item)
                else:
                    _extract_rows_from_value(item, rows)
        else:
            for item in value[:200]:
                _extract_rows_from_value(item, rows)
        return
    if isinstance(value, dict):
        if _has_survival_evidence(value):
            rows.append(value)
            return
        preferred_keys = (
            "turns",
            "rows",
            "timeline",
            "transcript",
            "turn_rows",
            "results",
            "scenario_results",
            "records",
            "transcript_rows",
        )
        for key in preferred_keys:
            nested = value.get(key)
            if nested is not None:
                _extract_rows_from_value(nested, rows)
        if not rows:
            for nested in list(value.values())[:100]:
                _extract_rows_from_value(nested, rows)


def _load_json_text(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    return json.loads(text)


def collect_survival_report_rows(results_dir: str | Path, *, zip_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    results_dir = Path(results_dir)
    rows: List[Dict[str, Any]] = []
    json_files = sorted(
        [path for path in results_dir.rglob("*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:_MAX_JSON_FILES]
    for path in json_files:
        try:
            value = _load_json_text(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        _extract_rows_from_value(value, rows)
        if len(rows) >= _MAX_ROWS:
            return rows[:_MAX_ROWS]

    if zip_path and Path(zip_path).exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                json_names = [name for name in zf.namelist() if name.lower().endswith(".json")]
                for name in json_names[:_MAX_ZIP_JSON_MEMBERS]:
                    if name.endswith(SURVIVAL_METRICS_JSON_NAME) or name.endswith(PERFORMANCE_SUMMARY_JSON_NAME):
                        continue
                    try:
                        value = _load_json_text(zf.read(name).decode("utf-8"))
                    except Exception:
                        continue
                    _extract_rows_from_value(value, rows)
                    if len(rows) >= _MAX_ROWS:
                        return rows[:_MAX_ROWS]
        except Exception:
            return rows[:_MAX_ROWS]
    return rows[:_MAX_ROWS]


def find_latest_autoplay_zip(results_dir: str | Path) -> Optional[Path]:
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return None
    patterns = (
        "*autoplay*campaign*results*.zip",
        "*autoplay*.zip",
        "*campaign*results*.zip",
        "*.zip",
    )
    seen: set[Path] = set()
    candidates: List[Path] = []
    for pattern in patterns:
        for path in results_dir.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _zip_has_members(zip_path: Path, *, prefix: str, json_name: str, html_name: str) -> bool:
    if not zip_path.exists():
        return False
    normalized = prefix.strip().strip("/")
    json_member = f"{normalized}/{json_name}" if normalized else json_name
    html_member = f"{normalized}/{html_name}" if normalized else html_name
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            return json_member in names and html_member in names
    except Exception:
        return False


def _zip_has_survival_members(zip_path: Path, *, prefix: str = "survival") -> bool:
    return _zip_has_members(
        zip_path,
        prefix=prefix,
        json_name=SURVIVAL_METRICS_JSON_NAME,
        html_name=SURVIVAL_METRICS_HTML_NAME,
    )


def _zip_has_performance_members(zip_path: Path, *, prefix: str = "performance") -> bool:
    return _zip_has_members(
        zip_path,
        prefix=prefix,
        json_name=PERFORMANCE_SUMMARY_JSON_NAME,
        html_name=PERFORMANCE_SUMMARY_HTML_NAME,
    )


def run_autoplay_survival_report_writer_hook(
    *,
    script_path: str | Path,
    argv: Optional[Iterable[str]] = None,
    exit_code: Any = 0,
    results_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Append post-run report artifacts to the latest autoplay output ZIP."""
    try:
        output_dir = Path(results_dir) if results_dir else default_autoplay_results_dir(script_path)
        zip_path = find_latest_autoplay_zip(output_dir)
        runtime_turn_backfill = backfill_runtime_turn_results_from_console_log(output_dir)
        rows = collect_survival_report_rows(output_dir, zip_path=zip_path)
        runtime_turn_result_rows = load_runtime_turn_result_rows(output_dir)
        live_performance_summary = load_live_performance_summary(output_dir, zip_path=zip_path)
        performance_rows = append_live_performance_bridge_row([*rows, *runtime_turn_result_rows], live_performance_summary)
        result_path_diagnostics = write_result_path_diagnostics(output_dir, zip_path=zip_path)
        standalone = write_survival_report_artifacts(output_dir, rows)
        performance_standalone = write_autoplay_performance_artifacts(
            output_dir,
            performance_rows,
            run_summary=live_performance_summary,
        )
        zip_result: Dict[str, Any] = {
            "ok": False,
            "reason": "no_zip_found",
            "source": SURVIVAL_WRITER_HOOK_SOURCE,
        }
        performance_zip_result: Dict[str, Any] = {
            "ok": False,
            "reason": "no_zip_found",
            "source": SURVIVAL_WRITER_HOOK_SOURCE,
        }
        if zip_path is not None:
            if _zip_has_survival_members(zip_path, prefix="survival"):
                zip_result = {
                    "ok": True,
                    "skipped": True,
                    "reason": "zip_already_contains_survival_members",
                    "zip_path": str(zip_path),
                    "source": SURVIVAL_WRITER_HOOK_SOURCE,
                }
            else:
                zip_result = append_survival_report_artifacts_to_zip(zip_path, rows, prefix="survival")
            if _zip_has_performance_members(zip_path, prefix="performance"):
                performance_zip_result = {
                    "ok": True,
                    "skipped": True,
                    "reason": "zip_already_contains_performance_members",
                    "zip_path": str(zip_path),
                    "source": SURVIVAL_WRITER_HOOK_SOURCE,
                }
            else:
                performance_zip_result = append_autoplay_performance_artifacts_to_zip(
                    zip_path,
                    performance_rows,
                    run_summary=live_performance_summary,
                    prefix="performance",
                )
        size_guard_result = cap_oversized_autoplay_reports(
            output_dir,
            zip_paths=[zip_path] if zip_path else [],
        )
        manifest = attach_survival_artifact_manifest({}, standalone)
        manifest = attach_autoplay_performance_manifest(manifest, performance_standalone)
        manifest["autoplay_report_size_guard"] = size_guard_result
        manifest["autoplay_result_path_diagnostics"] = result_path_diagnostics
        manifest["runtime_turn_result_backfill"] = runtime_turn_backfill
        manifest["runtime_turn_result_rows_observed"] = len(runtime_turn_result_rows)
        if zip_result.get("ok"):
            manifest = attach_survival_artifact_manifest(manifest, zip_result)
        if performance_zip_result.get("ok"):
            manifest = attach_autoplay_performance_manifest(manifest, performance_zip_result)
        return {
            "ok": True,
            "exit_code": exit_code,
            "argv": list(argv or []),
            "results_dir": str(output_dir),
            "zip_path": str(zip_path) if zip_path else "",
            "rows_observed": len(rows),
            "runtime_turn_result_backfill": runtime_turn_backfill,
            "runtime_turn_result_rows_observed": len(runtime_turn_result_rows),
            "performance_rows_observed": len(performance_rows),
            "live_performance_summary_loaded": bool(live_performance_summary),
            "result_path_diagnostics": result_path_diagnostics,
            "standalone_result": standalone,
            "zip_result": zip_result,
            "performance_standalone_result": performance_standalone,
            "performance_zip_result": performance_zip_result,
            "size_guard_result": size_guard_result,
            "manifest": manifest,
            "source": SURVIVAL_WRITER_HOOK_SOURCE,
        }
    except Exception as exc:  # pragma: no cover - defensive post-run guard
        return {
            "ok": False,
            "exit_code": exit_code,
            "error": repr(exc),
            "source": SURVIVAL_WRITER_HOOK_SOURCE,
        }
