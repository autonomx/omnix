from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_web_platform_smoke_script_backend_mode() -> None:
    root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "scripts/smoke_web_platform.py", "--skip-web"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["/api/health"]["ok"] is True
    assert checks["mock-worker-health"]["ok"] is True
    assert checks["event-stream-route-registered"]["ok"] is True
    assert checks["openapi-schema-matches"]["ok"] is True
