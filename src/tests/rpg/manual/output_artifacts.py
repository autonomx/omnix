from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from tests.rpg.manual.constants import (
    MANUAL_HTML_DIR_NAME,
    MANUAL_LOG_CHUNK_DIR_NAME,
    MANUAL_LOG_CHUNK_SOFT_BYTES,
    OUTPUT_PATH,
    RESULTS_ZIP_PATH,
    SERVICE_OUTPUT_PATH,
    TEST_RESULTS_ROOT,
)
from tests.rpg.manual.output_state import _OUTPUT_LOCK, _OUTPUTS


def _emit(value: Any = "", channel: str = "main") -> None:
    text = "" if value is None else str(value)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    timestamped_text = f"[{timestamp}] {text}" if text else f"[{timestamp}]"
    print(timestamped_text, flush=True)
    with _OUTPUT_LOCK:
        _OUTPUTS.setdefault(channel, []).append(timestamped_text)


def _reset_output(channel: str | None = None) -> None:
    with _OUTPUT_LOCK:
        if channel is None:
            _OUTPUTS.clear()
            return
        _OUTPUTS[channel] = []


def clear_test_results_root() -> None:
    root = TEST_RESULTS_ROOT

    # Safety guard: only allow deleting a directory literally named test-results.
    if root.name != "test-results":
        raise RuntimeError(f"refusing_to_clear_unexpected_test_results_root:{root}")

    if root.exists():
        for child in root.iterdir():
            if child.name in {".gitkeep"}:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    root.mkdir(parents=True, exist_ok=True)

    with _OUTPUT_LOCK:
        _OUTPUTS.clear()


def _chunk_lines_for_soft_limit(lines: list[str], max_chunk_bytes: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = 0

    soft_limit = max(1, int(max_chunk_bytes or MANUAL_LOG_CHUNK_SOFT_BYTES))

    for line in lines:
        encoded_size = len((line + "\n").encode("utf-8"))
        if current and current_size + encoded_size > soft_limit:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(line)
        current_size += encoded_size

    if current:
        chunks.append(current)

    return chunks or [[]]


def _write_output(
    path: Path,
    channel: str = "main",
    *,
    max_chunk_bytes: int | None = None,
) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)

    with _OUTPUT_LOCK:
        lines = list(_OUTPUTS.get(channel, []))

    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{timestamp}] Wrote transcript to: {path.resolve()}", flush=True)

    total_bytes = len(text.encode("utf-8"))
    artifact: Dict[str, Any] = {
        "path": str(path),
        "channel": channel,
        "chunked": False,
        "total_bytes": total_bytes,
        "files": [str(path)],
        "chunk_count": 0,
    }

    if max_chunk_bytes and total_bytes > max_chunk_bytes:
        chunk_dir = path.parent / MANUAL_LOG_CHUNK_DIR_NAME / path.stem
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunks = _chunk_lines_for_soft_limit(lines, max_chunk_bytes)

        files = [str(path)]
        for idx, chunk_lines in enumerate(chunks, start=1):
            chunk_path = chunk_dir / f"{path.stem}__chunk_{idx:03d}.txt"
            chunk_path.write_text("\n".join(chunk_lines), encoding="utf-8")
            files.append(str(chunk_path))

        manifest_path = chunk_dir / f"{path.stem}__manifest.json"
        manifest = {
            "source": str(path),
            "channel": channel,
            "total_bytes": total_bytes,
            "chunk_count": len(chunks),
            "files": files,
        }
        import json

        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(str(manifest_path))

        artifact.update({
            "chunked": True,
            "files": files,
            "chunk_count": len(chunks),
            "manifest": str(manifest_path),
        })

    return artifact


def _write_all_outputs(
    mapping: Dict[str, Path],
    *,
    max_chunk_bytes: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for channel, path in mapping.items():
        results[channel] = _write_output(path, channel=channel, max_chunk_bytes=max_chunk_bytes)
    return results


def _write_current_transcript_outputs(
    *,
    max_chunk_bytes: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    with _OUTPUT_LOCK:
        channels = sorted(_OUTPUTS.keys())

    output_map: Dict[str, Path] = {}

    if "flat_summary" in channels:
        output_map["flat_summary"] = TEST_RESULTS_ROOT / "manual_rpg_llm_transcript__summary.txt"

    if "flat_legacy" in channels:
        output_map["flat_legacy"] = OUTPUT_PATH

    for channel in channels:
        if channel.startswith("flat_turn_"):
            suffix = channel.replace("flat_turn_", "turn_")
            output_map[channel] = TEST_RESULTS_ROOT / f"manual_rpg_llm_transcript__{suffix}.txt"

    if "service_summary" in channels:
        output_map["service_summary"] = TEST_RESULTS_ROOT / "manual_rpg_service_scenarios__summary.txt"

    if "service_legacy" in channels:
        output_map["service_legacy"] = SERVICE_OUTPUT_PATH

    for channel in channels:
        if not channel.startswith("service_"):
            continue
        if channel in {"service_summary", "service_legacy"}:
            continue
        scenario_name = channel.replace("service_", "", 1)
        output_map[channel] = TEST_RESULTS_ROOT / f"manual_rpg_service_scenarios__{scenario_name}.txt"

    return _write_all_outputs(output_map, max_chunk_bytes=max_chunk_bytes)


def _should_include_in_results_zip(path: Path) -> bool:
    parts = set(path.parts)
    if MANUAL_HTML_DIR_NAME in parts:
        return False
    if "__pycache__" in parts:
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".zip"}:
        return False
    return path.is_file()


def _is_result_zip_candidate(path: Path) -> bool:
    return _should_include_in_results_zip(path)


def write_results_zip(path: Path = RESULTS_ZIP_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(TEST_RESULTS_ROOT.rglob("*")):
            if item.resolve() == path.resolve():
                continue
            if not _is_result_zip_candidate(item):
                continue
            arcname = item.relative_to(TEST_RESULTS_ROOT).as_posix()
            zf.write(item, arcname)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{timestamp}] Wrote results zip to: {path.resolve()}", flush=True)


def _assert_zip_excludes_html(path: Path = RESULTS_ZIP_PATH) -> None:
    if not path.exists():
        return

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()

    html_names = [
        name
        for name in names
        if name.startswith(f"{MANUAL_HTML_DIR_NAME}/") or f"/{MANUAL_HTML_DIR_NAME}/" in name
    ]
    if html_names:
        raise AssertionError(f"results_zip_includes_html:{html_names[:20]}")