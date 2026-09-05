"""Governed browser adapter backed by Vercel Labs agent-browser.

Pi never receives the raw ``agent-browser`` executable.  Browser operations are
canonical Omnix capabilities dispatched here after RunSpec, approval and budget
checks.  The adapter adds agent-browser's own domain/network containment as a
second boundary and disables page-provided WebMCP tools.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import AssistantToolRequest, AssistantToolResult

_BROWSER_ACTIONS = {
    "browser.open",
    "browser.snapshot",
    "browser.click",
    "browser.fill",
    "browser.press",
    "browser.hover",
    "browser.select",
    "browser.scroll",
    "browser.wait",
    "browser.get_text",
    "browser.get_attribute",
    "browser.get_url",
    "browser.screenshot",
    "browser.assert_text_contains",
    "browser.assert_attribute_contains",
    "browser.assert_url_contains",
    "browser.close",
}
_ASSERTIONS = {
    "browser.assert_text_contains",
    "browser.assert_attribute_contains",
    "browser.assert_url_contains",
}
_INTERACTIVE = {
    "browser.click",
    "browser.fill",
    "browser.press",
    "browser.select",
}
_DEFAULT_ALLOWED_DOMAINS = ("localhost", "127.0.0.1", "::1")
_SAFE_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
)
_SELECTOR = re.compile(r"^.{1,1024}$", re.S)
_MAX_VALUE_CHARS = 16_000
_MAX_OUTPUT_CHARS = 50_000


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def agent_browser_command() -> str:
    return os.environ.get("OMNIX_AGENT_BROWSER_COMMAND", "agent-browser").strip() or "agent-browser"


def browser_available() -> bool:
    if not _flag("OMNIX_AGENT_BROWSER_ENABLED", True):
        return False
    command = agent_browser_command()
    if os.path.isabs(command) or os.sep in command or (os.altsep and os.altsep in command):
        return Path(command).is_file()
    return shutil.which(command) is not None


def browser_allowed_domains() -> tuple[str, ...]:
    raw = os.environ.get("OMNIX_AGENT_BROWSER_ALLOWED_DOMAINS", "").strip()
    if not raw:
        return _DEFAULT_ALLOWED_DOMAINS
    values: list[str]
    try:
        parsed = json.loads(raw)
        values = [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        values = raw.split(",")
    normalized = []
    for item in values:
        value = item.strip().casefold()
        if value and not any(ch.isspace() for ch in value):
            normalized.append(value)
    return tuple(dict.fromkeys(normalized)) or _DEFAULT_ALLOWED_DOMAINS


def _domain_allowed(hostname: str) -> bool:
    host = hostname.strip().casefold().rstrip(".")
    if not host:
        return False
    for pattern in browser_allowed_domains():
        candidate = pattern.strip().casefold().rstrip(".")
        if candidate.startswith("*."):
            suffix = candidate[2:]
            if host == suffix or host.endswith("." + suffix):
                return True
        elif host == candidate:
            return True
    return False


def _validate_open_url(value: object) -> str:
    url = str(value or "").strip()
    if url == "about:blank":
        return url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("browser.open requires an http(s) URL or about:blank")
    if parsed.username or parsed.password:
        raise ValueError("browser.open does not allow credentials embedded in URLs")
    if not _domain_allowed(parsed.hostname):
        raise ValueError("browser origin is outside OMNIX_AGENT_BROWSER_ALLOWED_DOMAINS")
    return url


def _session_name(session_id: str | None) -> str:
    digest = hashlib.sha256(str(session_id or "omnix").encode("utf-8")).hexdigest()[:20]
    return f"omnix-{digest}"


def _safe_text(value: object, *, field: str, max_chars: int = _MAX_VALUE_CHARS) -> str:
    text = str(value or "")
    if not text or len(text) > max_chars or "\x00" in text:
        raise ValueError(f"browser {field} is missing or too large")
    return text


def _safe_selector(value: object) -> str:
    selector = str(value or "").strip()
    if not selector or not _SELECTOR.fullmatch(selector):
        raise ValueError("browser selector is missing or too large")
    return selector


def _timeout_seconds() -> int:
    try:
        return max(5, min(int(os.environ.get("OMNIX_AGENT_BROWSER_TIMEOUT_SECONDS", "45")), 180))
    except ValueError:
        return 45


def _minimal_environment() -> dict[str, str]:
    source = os.environ
    env = {key: source[key] for key in _SAFE_ENV_KEYS if source.get(key)}
    executable = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH", "").strip()
    if executable:
        env["AGENT_BROWSER_EXECUTABLE_PATH"] = executable
    return env


def _base_argv(request: AssistantToolRequest) -> list[str]:
    return [
        agent_browser_command(),
        "--session",
        _session_name(request.session_id),
        "--allowed-domains",
        ",".join(browser_allowed_domains()),
        "--content-boundaries",
        "--max-output",
        str(_MAX_OUTPUT_CHARS),
        "--no-webmcp",
    ]


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_timeout_seconds(),
        env=_minimal_environment(),
    )


def _command_for(request: AssistantToolRequest) -> tuple[list[str], dict[str, Any]]:
    action = request.action_id
    payload = dict(request.input)
    argv = _base_argv(request)
    metadata: dict[str, Any] = {}

    if action == "browser.open":
        url = _validate_open_url(payload.get("url"))
        argv.extend(["open", url])
        metadata["url"] = url
    elif action == "browser.snapshot":
        argv.extend(["snapshot", "--json"])
    elif action == "browser.click":
        argv.extend(["click", _safe_selector(payload.get("selector"))])
    elif action == "browser.fill":
        argv.extend([
            "fill",
            _safe_selector(payload.get("selector")),
            _safe_text(payload.get("text"), field="text"),
        ])
    elif action == "browser.press":
        argv.extend(["press", _safe_text(payload.get("key"), field="key", max_chars=128)])
    elif action == "browser.hover":
        argv.extend(["hover", _safe_selector(payload.get("selector"))])
    elif action == "browser.select":
        argv.extend([
            "select",
            _safe_selector(payload.get("selector")),
            _safe_text(payload.get("value"), field="value", max_chars=2048),
        ])
    elif action == "browser.scroll":
        direction = str(payload.get("direction") or "down").strip().casefold()
        if direction not in {"up", "down", "left", "right"}:
            raise ValueError("browser.scroll direction must be up/down/left/right")
        argv.extend(["scroll", direction])
        pixels = payload.get("pixels")
        if pixels is not None:
            amount = int(pixels)
            if amount < 1 or amount > 100_000:
                raise ValueError("browser.scroll pixels outside allowed range")
            argv.append(str(amount))
    elif action == "browser.wait":
        supplied = [
            key for key in ("selector", "text", "url", "milliseconds", "load")
            if payload.get(key) not in {None, ""}
        ]
        if len(supplied) != 1:
            raise ValueError("browser.wait requires exactly one bounded wait condition")
        kind = supplied[0]
        if kind == "selector":
            argv.extend(["wait", _safe_selector(payload[kind])])
        elif kind == "text":
            argv.extend(["wait", "--text", _safe_text(payload[kind], field="text", max_chars=4096)])
        elif kind == "url":
            pattern = _safe_text(payload[kind], field="url pattern", max_chars=2048)
            argv.extend(["wait", "--url", pattern])
        elif kind == "load":
            state = str(payload[kind]).strip().casefold()
            if state not in {"load", "domcontentloaded", "networkidle"}:
                raise ValueError("browser.wait load state is not allowed")
            argv.extend(["wait", "--load", state])
        else:
            milliseconds = int(payload[kind])
            if milliseconds < 0 or milliseconds > 30_000:
                raise ValueError("browser.wait milliseconds outside allowed range")
            argv.extend(["wait", str(milliseconds)])
    elif action == "browser.get_text":
        argv.extend(["get", "text", _safe_selector(payload.get("selector"))])
    elif action == "browser.get_attribute":
        argv.extend([
            "get",
            "attr",
            _safe_selector(payload.get("selector")),
            _safe_text(payload.get("attribute"), field="attribute", max_chars=256),
        ])
    elif action == "browser.get_url":
        argv.extend(["get", "url"])
    elif action == "browser.screenshot":
        directory = Path(tempfile.gettempdir()) / "omnix-agent-browser"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{_session_name(request.session_id)}-{os.urandom(6).hex()}.png"
        argv.extend(["screenshot", str(target)])
        if bool(payload.get("full_page")):
            argv.append("--full")
        metadata["screenshot_path"] = str(target)
    elif action == "browser.assert_text_contains":
        argv.extend(["get", "text", _safe_selector(payload.get("selector"))])
        metadata["assertion_expected"] = _safe_text(
            payload.get("expected"), field="expected text", max_chars=4096
        )
    elif action == "browser.assert_attribute_contains":
        argv.extend([
            "get",
            "attr",
            _safe_selector(payload.get("selector")),
            _safe_text(payload.get("attribute"), field="attribute", max_chars=256),
        ])
        metadata["assertion_expected"] = _safe_text(
            payload.get("expected"), field="expected attribute", max_chars=4096
        )
    elif action == "browser.assert_url_contains":
        argv.extend(["get", "url"])
        metadata["assertion_expected"] = _safe_text(
            payload.get("expected"), field="expected URL", max_chars=4096
        )
    elif action == "browser.close":
        argv.append("close")
    else:
        raise ValueError("unsupported browser capability")
    return argv, metadata


def run_browser_tool_request(request: AssistantToolRequest) -> AssistantToolResult:
    if request.action_id not in _BROWSER_ACTIONS:
        return AssistantToolResult(
            tool_id="browser",
            action_id=request.action_id,
            session_id=request.session_id,
            result_summary="Unsupported governed browser action.",
            error="unsupported_browser_action",
        )
    if not browser_available():
        return AssistantToolResult(
            tool_id="browser",
            action_id=request.action_id,
            session_id=request.session_id,
            result_summary="agent-browser is not installed or is disabled.",
            error="browser_runtime_unavailable",
        )
    try:
        argv, metadata = _command_for(request)
        completed = _run(argv)
    except (ValueError, TypeError) as exc:
        return AssistantToolResult(
            tool_id="browser",
            action_id=request.action_id,
            session_id=request.session_id,
            result_summary="Browser request was rejected by Omnix policy.",
            error=f"browser_policy_rejected:{exc}",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AssistantToolResult(
            tool_id="browser",
            action_id=request.action_id,
            session_id=request.session_id,
            result_summary="agent-browser failed to execute.",
            error=f"browser_runtime_error:{type(exc).__name__}",
        )

    stdout = (completed.stdout or "")[:_MAX_OUTPUT_CHARS]
    stderr = (completed.stderr or "")[:8_000]
    if completed.returncode != 0:
        return AssistantToolResult(
            tool_id="browser",
            action_id=request.action_id,
            session_id=request.session_id,
            state_changed=False,
            result_summary=f"Browser action failed with exit code {completed.returncode}.",
            output={"stdout": stdout, "stderr": stderr, **metadata},
            error="browser_command_failed",
        )

    output: dict[str, Any] = {"stdout": stdout, **metadata}
    if request.action_id in _ASSERTIONS:
        expected = str(metadata.get("assertion_expected") or "")
        if expected not in stdout:
            return AssistantToolResult(
                tool_id="browser",
                action_id=request.action_id,
                session_id=request.session_id,
                state_changed=False,
                result_summary=f"Browser assertion failed for {request.action_id}.",
                output=output,
                error="browser_assertion_failed",
            )
        output["assertion_passed"] = True
    if request.action_id == "browser.snapshot" and stdout.strip():
        try:
            output["snapshot"] = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    screenshot_path = metadata.get("screenshot_path")
    if isinstance(screenshot_path, str):
        target = Path(screenshot_path)
        if target.is_file():
            data = target.read_bytes()
            output.update({
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })

    return AssistantToolResult(
        tool_id="browser",
        action_id=request.action_id,
        session_id=request.session_id,
        state_changed=request.action_id in _INTERACTIVE,
        result_summary=f"Completed governed browser action {request.action_id}.",
        output=output,
    )
