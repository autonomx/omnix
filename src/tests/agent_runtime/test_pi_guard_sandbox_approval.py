"""Safe commands are approved automatically only inside the sandbox (WP-4.7).

Runs the real guard extension under Node with a fake Pi API and a fake broker
that records which endpoints the guard calls.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "app" / "platform" / "agent_runtime" / "pi_guard_extension.ts"

SCRIPT = """
import { createServer } from "node:http";
import { pathToFileURL } from "node:url";

const calls = [];
const server = createServer((request, response) => {
  calls.push(new URL(request.url, "http://x").pathname.split("/").slice(4).join("/"));
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify({ allowed: true, passed: false }));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
process.env.OMNIX_AGENT_BROKER_URL = `http://127.0.0.1:${server.address().port}/api/agent-runs`;
const guard = (await import(pathToFileURL(process.argv[2]).href)).default;
const handlers = {};
guard({ on: (name, handler) => { handlers[name] = handler; } });
const result = await handlers.tool_call({
  toolName: "bash", toolCallId: "call-1", input: { command: "git status", cwd: process.env.OMNIX_AGENT_WORKSPACE },
});
server.close();
console.log(JSON.stringify({ result: result ?? null, calls }));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    major, minor = (int(part) for part in version.lstrip("v").split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("node with --experimental-strip-types is required")
    return node


def _run_guard(tmp_path: Path, *, sandboxed: bool) -> dict:
    node = _node()
    script = tmp_path / "harness.mjs"
    script.write_text(SCRIPT, encoding="utf-8")
    token = base64.urlsafe_b64encode(json.dumps({"run_id": "run-1", "exp": int(time.time()) + 900}).encode()).rstrip(b"=").decode()
    env = {
        **os.environ,
        "OMNIX_AGENT_RUN_ID": "run-1",
        "OMNIX_AGENT_RUN_TOKEN": f"{token}.signature",
        "OMNIX_AGENT_WORKSPACE": str(tmp_path),
        "OMNIX_AGENT_APPROVAL_POLICY": "ask_sensitive",
        "OMNIX_AGENT_LOCAL_CAPABILITIES": json.dumps(["workspace.read", "workspace.command"]),
        "OMNIX_AGENT_EXTERNAL_CAPABILITIES": "[]",
        "OMNIX_AGENT_ALLOWED_PATHS": json.dumps(["**"]),
        "OMNIX_AGENT_FORBIDDEN_PATHS": "[]",
        "OMNIX_AGENT_PATH_ROOTS": json.dumps([{"root_id": "workspace", "path": str(tmp_path), "access": "read_write"}]),
    }
    env.pop("OMNIX_AGENT_SANDBOXED", None)
    if sandboxed:
        env["OMNIX_AGENT_SANDBOXED"] = "1"
    completed = subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(script), str(GUARD)],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_a_safe_command_runs_without_approval_inside_the_sandbox(tmp_path) -> None:
    outcome = _run_guard(tmp_path, sandboxed=True)
    assert outcome["result"] is None
    # The guard did reach the broker for its other checks, just not for approval.
    assert "budget/tool" in outcome["calls"]
    assert "command-authorization" not in outcome["calls"]


def test_the_same_command_asks_for_approval_outside_the_sandbox(tmp_path) -> None:
    outcome = _run_guard(tmp_path, sandboxed=False)
    assert "command-authorization" in outcome["calls"]
