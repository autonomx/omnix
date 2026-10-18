"""The sandbox relay forwards only agent-runtime routes (WP-4.7).

Runs the real relay script under Node against a recording HTTP server.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import threading

import httpx
import pytest

from app.platform.agent_runtime import isolation

RELAY = Path(isolation.__file__).resolve().parent / "sandbox_relay.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _wait_until_listening(process: subprocess.Popen) -> None:
    """The relay prints one line per route once it listens; an early exit fails the test."""
    assert process.stdout is not None
    announced = process.stdout.readline()
    if not announced.startswith("relay "):
        pytest.fail(f"relay did not start: {process.stderr.read() if process.stderr else ''}")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def relay():
    seen: list[tuple[str, str, str | None]] = []

    class Upstream(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
            seen.append((self.command, self.path, self.headers.get("x-omnix-sandbox-relay")))
            reply = b'{"ok":true,"echo":' + str(len(body)).encode() + b"}"
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        do_GET = do_POST = _answer

        def log_message(self, *args: object) -> None:
            return

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    listen = _free_port()
    arguments = isolation.relay_arguments([(listen, f"127.0.0.1:{upstream.server_address[1]}")])
    process = subprocess.Popen(["node", str(RELAY), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_until_listening(process)
    try:
        yield f"http://127.0.0.1:{listen}", seen
    finally:
        process.terminate()
        process.wait(timeout=10)
        upstream.shutdown()


def test_agent_routes_are_forwarded_and_marked(relay) -> None:
    base, seen = relay
    response = httpx.post(f"{base}/api/agent-runs/run-1/run-token?x=1", json={"a": 1},
                          headers={"x-omnix-sandbox-relay": "forged-by-agent"})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert httpx.get(f"{base}/api/agent-model/v1/models").status_code == 200
    # The relay's own marker replaces whatever the agent sent.
    assert seen == [("POST", "/api/agent-runs/run-1/run-token?x=1", "1"), ("GET", "/api/agent-model/v1/models", "1")]


@pytest.mark.parametrize("path", [
    "/api/agent-runs/run-1/commands",           # approve or reject its own run
    "/api/assistant/tools/config",              # loosen tool approval
    "/api/agent-runs/run-1/run-token/../commands",
    "/api/agent-runs/run-1%2Fcommands/run-token",
    "/api/agent-runs/run-1/%2e%2e/commands",
    "/",
])
def test_every_other_route_is_refused_before_the_gateway(relay, path) -> None:
    base, seen = relay
    with httpx.Client() as client:
        request = client.build_request("POST", base, json={"command_type": "approve"})
        request.url = request.url.copy_with(raw_path=path.encode())
        response = client.send(request)
    assert (response.status_code, response.json()["detail"]) == (403, "sandbox_route_refused")
    assert seen == []


def test_protocol_upgrades_are_never_relayed(relay) -> None:
    base, seen = relay
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as connection:
        connection.sendall(
            b"GET /api/agent-model/v1/stream HTTP/1.1\r\nHost: x\r\nConnection: Upgrade\r\n"
            b"Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
        )
        assert connection.recv(1024) == b""
    assert seen == []


def test_the_preview_ingress_mode_forwards_raw_bytes() -> None:
    """``--tcp`` is the preview's ingress (dev server and websocket reload)."""
    upstream = socket.socket()
    upstream.bind(("127.0.0.1", 0))
    upstream.listen(1)
    listen = _free_port()
    process = subprocess.Popen(
        ["node", str(RELAY), "--tcp", f"{listen}=127.0.0.1:{upstream.getsockname()[1]}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _wait_until_listening(process)
        with socket.create_connection(("127.0.0.1", listen), timeout=5) as client:
            accepted, _ = upstream.accept()
            with accepted:
                client.sendall(b"GET /@vite/client HTTP/1.1\r\nUpgrade: websocket\r\n\r\n")
                assert accepted.recv(1024).startswith(b"GET /@vite/client")
    finally:
        process.terminate()
        process.wait(timeout=10)
        upstream.close()


def test_the_relay_refuses_to_start_without_a_mode() -> None:
    completed = subprocess.run(["node", str(RELAY), "8000=127.0.0.1:8001"], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 2 and "--allow" in completed.stderr
