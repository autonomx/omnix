"""Bundle BI — direct autoplay survival report writer hook.

The named autoplay fragments are combined dynamically by
``autoplay_llm_campaign.py``.  Rather than patching an opaque fragment, this hook
runs after the stable wrapper's ``main()`` returns and enriches the generated
artifact directory/ZIP with the BH survival metrics files.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

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


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _repo_root_from_script(script_path: str | Path) -> Path:
    path = Path(script_path).resolve()
    for parent in [path.parent, *path.parents]:
        if (parent / "src").exists() and (parent / "resources").exists():
            return parent
    # src/tests/rpg/autoplay_llm_campaign.py -> repo root is parents[3]
    try:
        return path.parents[3]
    except IndexError:
        return path.parent


def default_autoplay_results_dir(script_path: str | Path) -> Path:
    return _repo_root_from_script(script_path) / "resources" / "data" / "test-results"


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
                if _has_survival_evidence(item) or any(k in item for k in ("turn", "turn_index", "tick", "turn_contract", "result")):
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
                    if name.endswith(SURVIVAL_METRICS_JSON_NAME):
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


def _zip_has_survival_members(zip_path: Path, *, prefix: str = "survival") -> bool:
    if not zip_path.exists():
        return False
    json_member = f"{prefix.strip('/')}/{SURVIVAL_METRICS_JSON_NAME}" if prefix else SURVIVAL_METRICS_JSON_NAME
    html_member = f"{prefix.strip('/')}/{SURVIVAL_METRICS_HTML_NAME}" if prefix else SURVIVAL_METRICS_HTML_NAME
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            return json_member in names and html_member in names
    except Exception:
        return False


def run_autoplay_survival_report_writer_hook(
    *,
    script_path: str | Path,
    argv: Optional[Iterable[str]] = None,
    exit_code: Any = 0,
    results_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Append survival report artifacts to the latest autoplay output ZIP.

    Returns a diagnostic payload and never raises for normal missing-artifact
    cases.  The wrapper catches unexpected exceptions too, so this hook cannot
    fail the autoplay run after gameplay/tests already completed.
    """
    try:
        output_dir = Path(results_dir) if results_dir else default_autoplay_results_dir(script_path)
        zip_path = find_latest_autoplay_zip(output_dir)
        rows = collect_survival_report_rows(output_dir, zip_path=zip_path)
        standalone = write_survival_report_artifacts(output_dir, rows)
        zip_result: Dict[str, Any] = {
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
                zip_result = append_survival_report_artifacts_to_zip(
                    zip_path,
                    rows,
                    prefix="survival",
                )
        manifest = attach_survival_artifact_manifest({}, standalone)
        if zip_result.get("ok"):
            manifest = attach_survival_artifact_manifest(manifest, zip_result)
        return {
            "ok": True,
            "exit_code": exit_code,
            "argv": list(argv or []),
            "results_dir": str(output_dir),
            "zip_path": str(zip_path) if zip_path else "",
            "rows_observed": len(rows),
            "standalone_result": standalone,
            "zip_result": zip_result,
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
