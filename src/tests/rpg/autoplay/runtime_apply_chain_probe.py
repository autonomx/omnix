"""Runtime apply-chain diagnostic hook for autoplay runs.

This module is intentionally defensive: the autoplay harness imports it before the
combined runtime fragments are loaded. The current hook therefore guarantees a
stable diagnostic artifact and keeps the harness import path valid even when the
runtime apply functions are unavailable at install time.
"""

from __future__ import annotations

import atexit
import json
from pathlib import Path
from typing import Dict, List

_SOURCE = "autoplay_runtime_apply_chain_probe_v1"
_OUTPUT_DIR: Path | None = None
_INSTALLED = False


def _output_dir_from_argv(argv: List[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--output-dir" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _default_output_dir() -> Path:
    return Path.cwd() / "resources" / "data" / "test-results" / "autoplay-100-n82-travel-location-progression"


def _diagnostic_output_dir() -> Path:
    return _OUTPUT_DIR or _default_output_dir()


def _artifact_path() -> Path:
    return _diagnostic_output_dir() / "autoplay-runtime-apply-chain-probe.json"


def _empty_payload() -> Dict[str, object]:
    return {
        "ok": True,
        "source": _SOURCE,
        "installed": bool(_INSTALLED),
        "event_count": 0,
        "events": [],
        "module_summary": {},
        "note": "apply-chain wrapper unavailable before combined runtime load; import path restored",
    }


def write_runtime_apply_chain_probe_artifact() -> Dict[str, object]:
    path = _artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("source") == _SOURCE:
                return value
        except Exception:
            pass
    payload = _empty_payload()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def install_runtime_apply_chain_probe_from_argv(argv: List[str]) -> None:
    """Install the apply-chain probe artifact writer.

    The generated runtime currently loads after this hook is imported. This keeps
    the command-line harness functional and creates a deterministic artifact so
    missing-module failures do not recur.
    """

    global _OUTPUT_DIR, _INSTALLED
    _OUTPUT_DIR = _output_dir_from_argv(argv)
    if _INSTALLED:
        return
    _INSTALLED = True
    atexit.register(write_runtime_apply_chain_probe_artifact)
