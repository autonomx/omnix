"""The Pi run token never reaches tool child processes (WP-4.6).

Runs the real ``pi_run_token.ts`` under Node's type stripping.
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

HELPER = Path(__file__).resolve().parents[2] / "app" / "agent_runtime" / "pi_run_token.ts"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    major, minor = (int(part) for part in version.lstrip("v").split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("node with --experimental-strip-types is required")
    return node


def _token(expires_in: int) -> str:
    payload = json.dumps({"run_id": "run-1", "exp": int(time.time()) + expires_in}).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode() + ".signature"


SCRIPT = """
import { createServer } from "node:http";
import { execFileSync } from "node:child_process";
import { onRunTokenRenewed, runAuthorization, runTokenState } from "__HELPER__";

const before = runTokenState().token;
const inEnvironment = process.env.OMNIX_AGENT_RUN_TOKEN ?? null;
const child = execFileSync(process.execPath, ["-e", "process.stdout.write(process.env.OMNIX_AGENT_RUN_TOKEN || '')"], {
  env: process.env,
}).toString();
// A second extension loading later shares the same slot.
const shared = runTokenState().token === before;

const server = createServer((request, response) => {
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify({ token: "renewed", expires_at: Math.floor(Date.now() / 1000) + 900 }));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const renewedTo = [];
onRunTokenRenewed((token) => renewedTo.push(token));
const header = await runAuthorization(`http://127.0.0.1:${port}`, "run-1");
server.close();
console.log(JSON.stringify({ before, inEnvironment, child, shared, header, renewedTo }));
"""


def test_token_leaves_the_environment_and_renews_before_expiry(tmp_path) -> None:
    node = _node()
    script = tmp_path / "probe.ts"
    script.write_text(SCRIPT.replace("__HELPER__", HELPER.as_uri()), encoding="utf-8")
    token = _token(expires_in=60)  # inside the renewal window
    result = subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(script)],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
             "OMNIX_AGENT_RUN_TOKEN": token},
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed["before"] == token
    assert observed["inEnvironment"] is None
    assert observed["child"] == ""
    assert observed["shared"] is True
    assert observed["header"] == "OmnixRun renewed"
    assert observed["renewedTo"] == ["renewed"]


def test_extensions_take_the_token_when_they_load() -> None:
    root = HELPER.parent
    for name in ("pi_broker_extension.ts", "pi_guard_extension.ts", "pi_model_provider_extension.ts"):
        source = (root / name).read_text(encoding="utf-8")
        assert 'from "./pi_run_token.ts"' in source, name
        assert "runTokenState()" in source, name
        assert "X-Omnix-Agent-Run-Id" not in source or "apiKey: token" in source, name
    broker = (root / "pi_broker_extension.ts").read_text(encoding="utf-8")
    guard = (root / "pi_guard_extension.ts").read_text(encoding="utf-8")
    # Every broker call carries the token.
    assert broker.count("fetch(") == broker.count("Authorization: await runAuthorization(baseUrl, runId)")
    assert guard.count("fetch(") == guard.count("Authorization: await runAuthorization(brokerUrl, runId)")
