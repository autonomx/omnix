from __future__ import annotations

import html
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from app.launcher.service_manager import LAUNCHER_MANAGER_VERSION, get_default_manager

app = FastAPI(title="Omnix Launcher Control", version=LAUNCHER_MANAGER_VERSION)

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
    button:disabled { opacity:.45; cursor:not-allowed; }
    pre { white-space:pre-wrap; overflow:auto; max-height:240px; background:#0d1017; color:#d7e0ff; padding:10px; border-radius:10px; border:1px solid #272e3d; font-size:12px; }
    .toolbar { margin: 12px 0 18px; }
    .error { display:none; border:1px solid #704141; background:#2c1717; color:#ffd6d6; padding:10px; border-radius:10px; margin-bottom:14px; white-space:pre-wrap; }
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
  <div id="error" class="error"></div>
  <div class="toolbar">
    <button id="start-auto" type="button">Start enabled services</button>
    <button id="stop-all" class="stop" type="button">Stop all</button>
  </div>
  <div id="services" class="grid"></div>
<script>
(() => {
  const byId = (id) => document.getElementById(id);
  const servicesEl = byId('services');
  const errorEl = byId('error');
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

  async function api(path, options) {
    const response = await fetch(path, options || {});
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
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
  byId('stop-all').addEventListener('click', () => runAction('/api/services/stop-all'));
  servicesEl.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-service-id][data-action]');
    if (!button || button.disabled) return;
    const serviceId = encodeURIComponent(button.dataset.serviceId || '');
    const verb = encodeURIComponent(button.dataset.action || '');
    if (!serviceId || !verb) return;
    runAction(`/api/services/${serviceId}/${verb}`);
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
