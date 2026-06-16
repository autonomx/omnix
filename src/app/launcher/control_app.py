from __future__ import annotations

import html
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from app.launcher.service_manager import LAUNCHER_MANAGER_VERSION, get_default_manager

app = FastAPI(title="Omnix Launcher Control", version=LAUNCHER_MANAGER_VERSION)

_DEFAULT_APP_OPEN_URL = "http://localhost:5173/"


def _app_open_url() -> str:
    url = (
        os.environ.get("OMNIX_APP_OPEN_URL")
        or os.environ.get("OMNIX_APP_PRIVATE_URL")
        or _DEFAULT_APP_OPEN_URL
    ).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid OMNIX_APP_OPEN_URL: {url!r}")
    return url


def _candidate_browser_paths() -> list[str]:
    candidates: list[str] = []
    configured = os.environ.get("OMNIX_PRIVATE_BROWSER") or os.environ.get("OMNIX_BROWSER_EXE")
    if configured:
        candidates.append(configured)

    for executable in (
        "chrome",
        "chrome.exe",
        "msedge",
        "msedge.exe",
        "brave",
        "brave.exe",
        "firefox",
        "firefox.exe",
    ):
        found = shutil.which(executable)
        if found:
            candidates.append(found)

    if os.name == "nt":
        roots = [
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
        ]
        relative_paths = [
            ("Google", "Chrome", "Application", "chrome.exe"),
            ("Microsoft", "Edge", "Application", "msedge.exe"),
            ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ("Mozilla Firefox", "firefox.exe"),
        ]
        for root in roots:
            if not root:
                continue
            for parts in relative_paths:
                path = Path(root).joinpath(*parts)
                if path.exists():
                    candidates.append(str(path))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key and key not in seen:
            unique.append(str(candidate))
            seen.add(key)
    return unique


def _private_browser_command(browser_path: str, url: str) -> list[str]:
    name = Path(browser_path).name.casefold()
    if "firefox" in name:
        return [browser_path, "-private-window", url]
    if "msedge" in name:
        return [browser_path, "--new-window", "--inprivate", url]
    return [browser_path, "--new-window", "--incognito", url]


def _open_app_private_browser() -> dict[str, Any]:
    url = _app_open_url()
    errors: list[str] = []
    for browser_path in _candidate_browser_paths():
        command = _private_browser_command(browser_path, url)
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
            return {
                "ok": True,
                "url": url,
                "browser": browser_path,
                "private_mode": True,
            }
        except Exception as exc:
            errors.append(f"{browser_path}: {type(exc).__name__}: {exc}")

    return {
        "ok": False,
        "url": url,
        "error": "No supported browser executable was found. Set OMNIX_PRIVATE_BROWSER to chrome.exe, msedge.exe, brave.exe, or firefox.exe.",
        "details": errors,
    }

_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Omnix Launcher Control</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; background: #101216; color: #eef2ff; }
    body { margin: 0; padding: 24px; background: radial-gradient(circle at top, #1c2330, #101216 55%); }
    header { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:18px; }
    h1 { margin:0; font-size:24px; }
    h2 { margin:0; font-size:17px; }
    .sub { color:#aeb8cc; margin-top:6px; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px; }
    .card { border:1px solid #2a3142; border-radius:14px; background:#161a22dd; padding:14px; box-shadow:0 10px 28px #0006; }
    .row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
    .status { font-size:12px; padding:4px 8px; border-radius:999px; background:#303846; text-transform:uppercase; letter-spacing:.04em; }
    .status.running { background:#124d31; color:#adffd2; }
    .status.stopped, .status.exited { background:#4d3112; color:#ffd8ad; }
    .status.disabled { background:#352b3f; color:#d7c4ff; }
    .desc { color:#aeb8cc; min-height:36px; }
    button { border:0; border-radius:10px; padding:8px 10px; margin:3px; background:#32405a; color:#f6f7fb; cursor:pointer; }
    button:hover { background:#415476; }
    button.stop { background:#5a3332; }
    button.stop:hover { background:#774442; }
    button.copy { background:#2f4f66; }
    button.copy:hover { background:#3e6988; }
    button:disabled { opacity:.45; cursor:not-allowed; }
    pre { white-space:pre-wrap; overflow:auto; max-height:240px; background:#0d1017; color:#d7e0ff; padding:10px; border-radius:10px; border:1px solid #272e3d; font-size:12px; }
    .toolbar { margin: 12px 0 18px; }
    .error { display:none; border:1px solid #704141; background:#2c1717; color:#ffd6d6; padding:10px; border-radius:10px; margin-bottom:14px; white-space:pre-wrap; }
    .notice { display:none; border:1px solid #3f5d7b; background:#142237; color:#c9e2ff; padding:10px; border-radius:10px; margin-bottom:14px; white-space:pre-wrap; }
    .copy-source { position:fixed; left:-9999px; top:-9999px; width:1px; height:1px; opacity:0; }
    a { color:#9fc3ff; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Omnix Launcher Control</h1>
      <div class="sub">Start, stop, restart, and watch logs for local services from one window.</div>
    </div>
    <div><a href="/api/services" target="_blank" rel="noreferrer">JSON</a></div>
  </header>
  <div id="notice" class="notice"></div>
  <div id="error" class="error"></div>
  <textarea id="copy-source" class="copy-source" aria-hidden="true" tabindex="-1"></textarea>
  <div class="toolbar">
    <button id="start-auto" type="button">Start enabled services</button>
    <button id="open-app-private" type="button">Open app privately</button>
    <button id="stop-all" class="stop" type="button">Stop all</button>
  </div>
  <div id="services" class="grid"></div>
<script>
(() => {
  const byId = (id) => document.getElementById(id);
  const servicesEl = byId('services');
  const errorEl = byId('error');
  const noticeEl = byId('notice');
  const copySourceEl = byId('copy-source');
  let busy = false;

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[char]));
  }

  function showError(message) {
    if (!errorEl) return;
    const text = String(message || '').trim();
    errorEl.textContent = text;
    errorEl.style.display = text ? 'block' : 'none';
  }

  function showNotice(message) {
    if (!noticeEl) return;
    const text = String(message || '').trim();
    noticeEl.textContent = text;
    noticeEl.style.display = text ? 'block' : 'none';
    if (text) window.setTimeout(() => showNotice(''), 2500);
  }

  async function api(path, options) {
    const response = await fetch(path, options || {});
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  }

  async function textApi(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.text();
  }

  async function copyText(value) {
    const text = String(value || '');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    copySourceEl.value = text;
    copySourceEl.focus();
    copySourceEl.select();
    document.execCommand('copy');
  }

  async function copyLogs(serviceId, label) {
    if (!serviceId) return;
    showError('');
    try {
      const logs = await textApi(`/api/services/${encodeURIComponent(serviceId)}/logs?limit=500`);
      const header = `# Omnix launcher logs: ${label || serviceId}\n# Service id: ${serviceId}\n# Copied: ${new Date().toISOString()}\n\n`;
      await copyText(header + (logs || '[no logs yet]'));
      showNotice(`Copied logs for ${label || serviceId}`);
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    }
  }

  async function runAction(path) {
    if (busy) return;
    busy = true;
    showError('');
    try {
      await api(path, { method: 'POST' });
      await refresh();
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    } finally {
      busy = false;
    }
  }

  async function openAppPrivate() {
    if (busy) return;
    busy = true;
    showError('');
    try {
      const result = await api('/api/open-app-private', { method: 'POST' });
      showNotice(`Opened ${result.url || 'app'} in a private browser window`);
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    } finally {
      busy = false;
    }
  }

  function render(service) {
    const running = service.status === 'running';
    const disabled = service.status === 'disabled' || !service.enabled;
    const logs = (service.recent_logs || []).map(esc).join('\n');
    const id = esc(service.id);
    return `<section class="card">
      <div class="row"><h2>${esc(service.label)}</h2><span class="status ${esc(service.status)}">${esc(service.status)}</span></div>
      <p class="desc">${esc(service.description)}</p>
      <div>PID: ${esc(service.pid || '-')} · uptime: ${Math.round(service.uptime_seconds || 0)}s</div>
      <div style="margin:10px 0">
        <button type="button" data-service-id="${id}" data-action="start" ${running || disabled ? 'disabled' : ''}>Start</button>
        <button type="button" class="stop" data-service-id="${id}" data-action="stop" ${!running ? 'disabled' : ''}>Stop</button>
        <button type="button" data-service-id="${id}" data-action="restart" ${disabled ? 'disabled' : ''}>Restart</button>
        <button type="button" class="copy" data-service-id="${id}" data-service-label="${esc(service.label)}" data-action="copy-logs">Copy logs</button>
      </div>
      <pre>${logs || '[no logs yet]'}</pre>
    </section>`;
  }

  async function refresh() {
    try {
      const data = await api('/api/services');
      servicesEl.innerHTML = (data.services || []).map(render).join('');
      showError('');
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    }
  }

  byId('start-auto').addEventListener('click', () => runAction('/api/services/start-auto'));
  byId('open-app-private').addEventListener('click', openAppPrivate);
  byId('stop-all').addEventListener('click', () => runAction('/api/services/stop-all'));
  servicesEl.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-service-id][data-action]');
    if (!button || button.disabled) return;
    const serviceId = button.dataset.serviceId || '';
    const verb = button.dataset.action || '';
    if (!serviceId || !verb) return;
    if (verb === 'copy-logs') {
      copyLogs(serviceId, button.dataset.serviceLabel || serviceId);
      return;
    }
    runAction(`/api/services/${encodeURIComponent(serviceId)}/${encodeURIComponent(verb)}`);
  });

  refresh();
  window.setInterval(refresh, 2000);
})();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return _HTML


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/services")
def list_services() -> dict[str, Any]:
    manager = get_default_manager()
    return {"format_version": LAUNCHER_MANAGER_VERSION, "services": manager.list_services()}


@app.post("/api/services/start-auto")
def start_auto_services() -> dict[str, Any]:
    return get_default_manager().start_auto_services()


@app.post("/api/services/stop-all")
def stop_all_services() -> dict[str, Any]:
    return get_default_manager().stop_all()


@app.post("/api/open-app-private")
def open_app_private() -> dict[str, Any]:
    result = _open_app_private_browser()
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result)
    return result


@app.get("/api/services/{service_id}")
def service_status(service_id: str) -> dict[str, Any]:
    try:
        return get_default_manager().service_snapshot(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/start")
def start_service(service_id: str) -> dict[str, Any]:
    try:
        return get_default_manager().start(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/stop")
def stop_service(service_id: str) -> dict[str, Any]:
    try:
        return get_default_manager().stop(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/restart")
def restart_service(service_id: str) -> dict[str, Any]:
    try:
        return get_default_manager().restart(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/services/{service_id}/logs", response_class=PlainTextResponse)
def service_logs(service_id: str, limit: int = 300) -> str:
    try:
        return "\n".join(get_default_manager().logs(service_id, limit=limit))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.exception_handler(Exception)
def json_errors(_request: Any, exc: Exception) -> JSONResponse:
    safe = html.escape(f"{type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"ok": False, "error": safe})
