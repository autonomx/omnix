from __future__ import annotations

import html
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.launcher.service_manager import LAUNCHER_MANAGER_VERSION, get_default_manager

app = FastAPI(title="Omnix Launcher Control", version=LAUNCHER_MANAGER_VERSION)

_HTML = """
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
    a { color:#9fc3ff; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Omnix Launcher Control</h1>
      <div class="sub">Start, stop, restart, and watch logs for local services from one window.</div>
    </div>
    <div><a href="/api/services" target="_blank">JSON</a></div>
  </header>
  <div class="toolbar">
    <button onclick="startAuto()">Start enabled services</button>
    <button class="stop" onclick="stopAll()">Stop all</button>
  </div>
  <div id="services" class="grid"></div>
<script>
const $ = (id) => document.getElementById(id);
function esc(s){ return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
async function api(path, opts){ const r = await fetch(path, opts || {}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function action(id, verb){ await api(`/api/services/${encodeURIComponent(id)}/${verb}`, {method:'POST'}); await refresh(); }
async function startAuto(){ await api('/api/services/start-auto', {method:'POST'}); await refresh(); }
async function stopAll(){ await api('/api/services/stop-all', {method:'POST'}); await refresh(); }
function render(service){
  const running = service.status === 'running';
  const disabled = service.status === 'disabled' || !service.enabled;
  const logs = (service.recent_logs || []).map(esc).join('\n');
  return `<section class="card">
    <div class="row"><h2>${esc(service.label)}</h2><span class="status ${esc(service.status)}">${esc(service.status)}</span></div>
    <p class="desc">${esc(service.description)}</p>
    <div>PID: ${esc(service.pid || '-')} · uptime: ${Math.round(service.uptime_seconds || 0)}s</div>
    <div style="margin:10px 0">
      <button onclick="action('${esc(service.id)}','start')" ${running || disabled ? 'disabled' : ''}>Start</button>
      <button class="stop" onclick="action('${esc(service.id)}','stop')" ${!running ? 'disabled' : ''}>Stop</button>
      <button onclick="action('${esc(service.id)}','restart')" ${disabled ? 'disabled' : ''}>Restart</button>
    </div>
    <pre>${logs || '[no logs yet]'}</pre>
  </section>`;
}
async function refresh(){
  const data = await api('/api/services');
  $('services').innerHTML = data.services.map(render).join('');
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return _HTML


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
