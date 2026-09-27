from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.runtime.net import allowed_origins, bind_host

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def isolated_listener_env(monkeypatch):
    for key in ("OMNIX_BIND_HOST", "OMNIX_ALLOW_LAN", "OMNIX_ALLOWED_ORIGINS"):
        monkeypatch.delenv(key, raising=False)


def test_default_loopback():
    assert bind_host() == "127.0.0.1"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.2", "::1"])
def test_explicit_loopback(host):
    assert bind_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.2"])
def test_public_listener_requires_both_opt_ins(monkeypatch, host, caplog):
    with pytest.raises(ValueError):
        bind_host(host)
    monkeypatch.setenv("OMNIX_BIND_HOST", host)
    with pytest.raises(ValueError):
        bind_host()
    monkeypatch.setenv("OMNIX_ALLOW_LAN", "true")
    assert bind_host() == host
    assert "exposed beyond loopback" in caplog.text


def test_flag_alone_cannot_expose_listener(monkeypatch):
    monkeypatch.setenv("OMNIX_ALLOW_LAN", "true")
    with pytest.raises(ValueError):
        bind_host("192.168.1.2")


@pytest.mark.parametrize("host", ["", "example.com", "127.0.0.1:8000", "localhost.evil.test"])
def test_invalid_address(host):
    with pytest.raises(ValueError):
        bind_host(host)


@pytest.mark.parametrize("flag", ["1", "yes", "false", ""])
def test_lan_requires_true_literal(monkeypatch, flag):
    monkeypatch.setenv("OMNIX_BIND_HOST", "192.168.1.2")
    monkeypatch.setenv("OMNIX_ALLOW_LAN", flag)
    with pytest.raises(ValueError):
        bind_host()


def test_cors_defaults():
    assert allowed_origins() == [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ]


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "file:///tmp", "http://user:password@localhost", "http://localhost/path", "http://localhost:bad"])
def test_invalid_cors_origin(monkeypatch, origin):
    monkeypatch.setenv("OMNIX_ALLOWED_ORIGINS", origin)
    with pytest.raises(ValueError):
        allowed_origins()


def test_configured_origins(monkeypatch):
    monkeypatch.setenv("OMNIX_ALLOWED_ORIGINS", " https://omnix.example.com,https://omnix.example.com ")
    assert allowed_origins() == ["https://omnix.example.com"]


def test_launcher_propagates_listener_policy(monkeypatch):
    from app.launcher.service_manager import build_default_service_specs

    monkeypatch.setenv("OMNIX_BIND_HOST", "192.168.1.2")
    monkeypatch.setenv("OMNIX_ALLOW_LAN", "true")
    specs = {spec.service_id: spec for spec in build_default_service_specs(ROOT)}
    for spec in specs.values():
        assert spec.env["OMNIX_BIND_HOST"] == "192.168.1.2"
    for name in ("gateway", "image", "web"):
        command = specs[name].command
        assert command[command.index("--host") + 1] == "192.168.1.2"


def test_no_public_bind_literals_in_production_sources():
    violations = []
    for path in (ROOT / "src").rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        if path == ROOT / "src/app/runtime/net.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "0.0.0.0" in node.value:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    scripts = json.loads((ROOT / "src/apps/web/package.json").read_text())["scripts"]
    violations.extend(f"package.json:{name}" for name, command in scripts.items() if "0.0.0.0" in command and not name.endswith(":lan"))
    assert not violations, violations


def test_windows_startup_watchdog_sends_guard_header():
    source = (ROOT / "start_all.bat").read_text(encoding="utf-8")
    calls = source.split("Invoke-RestMethod -Method Post")[1:]
    assert len(calls) == 2
    for call in calls:
        assert call.startswith(" -Headers @{'X-Omnix-Client'='launcher'} -Uri")
    assert source.index("from app.runtime.net import bind_host") < source.index('start "Omnix Startup Check"')
