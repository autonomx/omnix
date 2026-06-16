from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_live_worker_endurance_script_requires_explicit_opt_in(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_worker_endurance.py",
            "--iterations",
            "1",
            "--interval-seconds",
            "0",
            "--output-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["skipped"] is True
    assert payload["error"] == "live_worker_endurance_requires_allow_live"


def test_live_worker_endurance_script_writes_mock_worker_artifact(tmp_path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    env["OMNIX_GATEWAY_MOCK_WORKERS"] = "1"
    env["OMNIX_GATEWAY_MOCK_WORKERS_LIST"] = "tts,stt,image"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_worker_endurance.py",
            "--allow-live",
            "--allow-mock",
            "--iterations",
            "2",
            "--interval-seconds",
            "0",
            "--min-reachable",
            "3",
            "--output-dir",
            str(tmp_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    artifact_path = Path(payload["artifact_path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["format_version"] == "omnix_web_live_worker_endurance_v1"
    assert payload["iterations"] == 2
    assert payload["minimum_reachable_seen"] == 3
    assert len(payload["samples"]) == 2
    assert artifact["artifact_path"] == payload["artifact_path"]
    assert artifact["samples"][0]["summary"]["mocked"] == 3
