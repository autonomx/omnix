"""CI-safe smoke checks for the Omnix web platform."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": " ".join(command),
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _gateway_smoke(root: Path) -> list[dict[str, Any]]:
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    os.environ.setdefault("OMNIX_GATEWAY_MOCK_WORKERS", "1")
    os.environ.setdefault("OMNIX_GATEWAY_MOCK_WORKERS_LIST", "tts,stt,image")

    from fastapi.testclient import TestClient

    from app.gateway.main import create_gateway_app

    app = create_gateway_app()
    client = TestClient(app, raise_server_exceptions=False)
    checks: list[dict[str, Any]] = []

    for path in ["/api/health", "/api/runtime/status", "/api/workers/health", "/api/diagnostics"]:
        response = client.get(path)
        checks.append(
            {
                "name": path,
                "ok": response.status_code == 200,
                "status_code": response.status_code,
            }
        )

    workers = client.get("/api/workers/health").json()
    checks.append(
        {
            "name": "mock-worker-health",
            "ok": workers.get("summary", {}).get("mocked") == 3 and workers.get("ok") is True,
            "payload": workers,
        }
    )

    checks.append(
        {
            "name": "event-stream-route-registered",
            "ok": any(getattr(route, "path", "") == "/events" for route in app.routes),
        }
    )

    checked_in_schema = json.loads((root / "src/apps/web/src/api/generated/openapi.json").read_text(encoding="utf-8"))
    live_schema = create_gateway_app().openapi()
    checks.append(
        {
            "name": "openapi-schema-matches",
            "ok": checked_in_schema == live_schema,
        }
    )
    return checks


def _web_smoke(root: Path, *, build: bool) -> list[dict[str, Any]]:
    npm = _npm_cmd()
    checks = [
        _run([npm, "--workspace", "@omnix/web", "run", "typecheck"], cwd=root),
        _run([npm, "--workspace", "@omnix/web", "run", "test"], cwd=root),
        _run([npm, "--workspace", "@omnix/web", "run", "api:check"], cwd=root),
    ]
    if build:
        checks.append(_run([npm, "--workspace", "@omnix/web", "run", "build"], cwd=root))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-web", action="store_true", help="Only run gateway/backend smoke checks.")
    parser.add_argument("--web-build", action="store_true", help="Also run the Vite production build.")
    args = parser.parse_args(argv)

    root = _repo_root()
    checks = _gateway_smoke(root)
    if not args.skip_web:
        checks.extend(_web_smoke(root, build=args.web_build))

    ok = all(check.get("ok") is True for check in checks)
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
