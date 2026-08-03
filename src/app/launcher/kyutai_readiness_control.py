from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException

from app.launcher.service_manager import get_default_manager

_ROUTE_SENTINEL = "_omnix_kyutai_readiness_controls_registered"
_DEFAULT_ADAPTER_URL = "http://127.0.0.1:5202"
_MAX_RESPONSE_BYTES = 128 * 1024

_REASON_MESSAGES = {
    "upstream_connection_refused": (
        "Moshi is not accepting connections on port 8090. Confirm the Docker STT container is running."
    ),
    "upstream_connection_closed": (
        "Moshi accepted the connection but closed it before a usable Ready session was established. "
        "Inspect the moshi-server card logs for model, API-key, or protocol errors."
    ),
    "upstream_connect_timeout": (
        "Moshi did not complete its Ready handshake before the timeout. The model may still be loading "
        "or the container may be stalled."
    ),
    "upstream_auth_rejected": (
        "Moshi rejected authentication. Verify the Hugging Face token and the configured Kyutai API key."
    ),
    "upstream_endpoint_not_found": (
        "The configured Moshi server does not expose /api/asr-streaming. Verify the pinned Unmute checkout."
    ),
    "upstream_rate_limited": "The upstream service is rate-limiting readiness probes.",
    "upstream_service_unavailable": (
        "Moshi returned a service-unavailable response. Inspect the container logs and GPU state."
    ),
    "upstream_tls_error": "The adapter could not validate the upstream TLS connection.",
    "upstream_client_incompatible": (
        "The installed websockets package is incompatible with the Kyutai adapter."
    ),
    "upstream_protocol_error": (
        "Moshi returned an unexpected WebSocket or MessagePack protocol response."
    ),
    "upstream_service_rejected": "Moshi explicitly rejected the STT session.",
    "upstream_dns_error": "The configured Moshi host could not be resolved.",
    "upstream_probe_failed": (
        "The Kyutai readiness probe failed without a more specific safe classification."
    ),
    "model_not_warm": "The adapter has not completed a recent successful Ready handshake.",
    "upstream_not_ready": "The adapter cannot currently establish a usable Moshi session.",
    "language_not_supported": "The selected language is not supported by the Kyutai model.",
}


def _adapter_base_url() -> str:
    return os.environ.get("OMNIX_KYUTAI_ADAPTER_URL", _DEFAULT_ADAPTER_URL).rstrip("/")


def _request_timeout_seconds() -> float:
    try:
        return max(0.25, min(15.0, float(os.environ.get("OMNIX_KYUTAI_STATUS_TIMEOUT_SECONDS", "3"))))
    except ValueError:
        return 3.0


def _fetch_adapter_json(path: str, *, query: dict[str, str] | None = None) -> dict[str, Any]:
    suffix = f"?{urlencode(query)}" if query else ""
    url = f"{_adapter_base_url()}{path}{suffix}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=_request_timeout_seconds()) as response:  # noqa: S310 - fixed local adapter URL
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"adapter_http_{exc.code}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"adapter_unreachable:{type(reason).__name__}") from exc
    except TimeoutError as exc:
        raise RuntimeError("adapter_timeout") from exc
    except OSError as exc:
        raise RuntimeError(f"adapter_unreachable:{type(exc).__name__}") from exc

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise RuntimeError("adapter_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("adapter_invalid_json") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("adapter_invalid_payload")
    return payload


def _service_snapshot(service_id: str) -> dict[str, Any]:
    try:
        snapshot = get_default_manager().service_snapshot(service_id)
    except KeyError:
        return {
            "id": service_id,
            "status": "missing",
            "enabled": False,
            "pid": None,
            "uptime_seconds": 0.0,
            "last_returncode": None,
        }
    return {
        "id": service_id,
        "status": snapshot.get("status"),
        "enabled": bool(snapshot.get("enabled")),
        "pid": snapshot.get("pid"),
        "uptime_seconds": snapshot.get("uptime_seconds", 0.0),
        "last_returncode": snapshot.get("last_returncode"),
    }


def _safe_health(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "ok": bool(payload.get("ok")),
        "provider": payload.get("provider"),
        "state": payload.get("state"),
        "upstream_ready": bool(payload.get("upstream_ready")),
        "last_ready_at": payload.get("last_ready_at"),
        "last_error_code": payload.get("last_error_code"),
        "last_error_type": payload.get("last_error_type"),
        "last_error_stage": payload.get("last_error_stage"),
        "failures_in_window": payload.get("failures_in_window"),
        "attempts_in_window": payload.get("attempts_in_window"),
        "retry_after_seconds": payload.get("retry_after_seconds"),
        "sample_rate": payload.get("sample_rate"),
        "frame_samples": payload.get("frame_samples"),
    }


def _safe_authority(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    reasons = payload.get("reasons")
    return {
        "ok": bool(payload.get("ok")),
        "eligible": bool(payload.get("eligible")),
        "mode": payload.get("mode"),
        "provider": payload.get("provider"),
        "upstream_ready": bool(payload.get("upstream_ready")),
        "model_warm": bool(payload.get("model_warm")),
        "language_supported": bool(payload.get("language_supported")),
        "quality_gate_passed": bool(payload.get("quality_gate_passed")),
        "contention_gate_passed": bool(payload.get("contention_gate_passed")),
        "reasons": [str(item) for item in reasons] if isinstance(reasons, list) else [],
    }


def _primary_reason(authority: dict[str, Any] | None, health: dict[str, Any] | None) -> str | None:
    reasons = authority.get("reasons", []) if authority else []
    for reason in reasons:
        if reason not in {"upstream_not_ready", "model_not_warm"}:
            return str(reason)
    if health and health.get("last_error_code"):
        return str(health["last_error_code"])
    return str(reasons[0]) if reasons else None


def _derive_summary(
    *,
    moshi: dict[str, Any],
    adapter: dict[str, Any],
    health: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    adapter_error: str | None,
) -> tuple[str, str, str | None]:
    if not moshi.get("enabled") and not adapter.get("enabled"):
        return "disabled", "Kyutai services are disabled in this launcher.", None
    if moshi.get("status") != "running":
        return "stopped", "Kyutai moshi-server is not running. Start or restart the Kyutai stack.", None
    if adapter.get("status") != "running":
        return "stopped", "Kyutai STT Adapter is not running. Start or restart the Kyutai stack.", None
    if adapter_error:
        return (
            "unreachable",
            "The launcher cannot reach the Kyutai adapter on port 5202 yet. It may still be starting.",
            adapter_error,
        )
    if authority and authority.get("eligible"):
        return (
            "ready",
            "Kyutai is ready, warm, and eligible for authority=test live-call measurements.",
            None,
        )

    reason = _primary_reason(authority, health)
    if reason:
        return "blocked", _REASON_MESSAGES.get(reason, f"Kyutai is blocked by {reason}."), reason
    return "starting", "Kyutai is running but has not completed a successful readiness probe yet.", None


def build_kyutai_readiness_status(*, force_probe: bool = False) -> dict[str, Any]:
    language = os.environ.get("OMNIX_LIVE_STT_LANGUAGE", "en").strip() or "en"
    mode = os.environ.get("OMNIX_KYUTAI_AUTHORITY_MODE", "test").strip() or "test"
    moshi = _service_snapshot("kyutai_moshi")
    adapter = _service_snapshot("kyutai_stt")

    health_payload: dict[str, Any] | None = None
    authority_payload: dict[str, Any] | None = None
    adapter_error: str | None = None
    if adapter.get("status") == "running":
        try:
            health_payload = _fetch_adapter_json(
                "/healthz",
                query={"force": "true"} if force_probe else None,
            )
            authority_payload = _fetch_adapter_json(
                "/authorityz",
                query={"language": language, "mode": mode},
            )
        except RuntimeError as exc:
            adapter_error = str(exc)

    health = _safe_health(health_payload)
    authority = _safe_authority(authority_payload)
    state, message, failure_code = _derive_summary(
        moshi=moshi,
        adapter=adapter,
        health=health,
        authority=authority,
        adapter_error=adapter_error,
    )
    return {
        "checked_at": time.time(),
        "state": state,
        "message": message,
        "failure_code": failure_code,
        "adapter_error": adapter_error,
        "language": language,
        "authority_mode": mode,
        "services": {"moshi": moshi, "adapter": adapter},
        "health": health,
        "authority": authority,
    }


def _restart_stack() -> dict[str, Any]:
    manager = get_default_manager()
    results: dict[str, Any] = {}
    for service_id in ("kyutai_moshi", "kyutai_stt"):
        try:
            results[service_id] = manager.restart(service_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"{service_id} is not registered in this launcher.",
            ) from exc
    return {
        "ok": all(bool(result.get("ok")) for result in results.values()),
        "services": results,
        "message": (
            "Kyutai moshi-server and adapter were restarted. Model startup may take several minutes; "
            "the readiness panel will update automatically."
        ),
    }


def register_kyutai_readiness_controls(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/launcher/kyutai-readiness")
    def get_kyutai_readiness() -> dict[str, Any]:
        return build_kyutai_readiness_status(force_probe=False)

    @app.post("/api/launcher/kyutai-readiness/probe")
    def probe_kyutai_readiness() -> dict[str, Any]:
        return build_kyutai_readiness_status(force_probe=True)

    @app.post("/api/launcher/kyutai-readiness/restart")
    def restart_kyutai_stack() -> dict[str, Any]:
        return _restart_stack()


def enhance_launcher_html(source: str) -> str:
    if 'id="kyutai-readiness-panel"' in source:
        return source

    css_marker = "    .toolbar { margin: 12px 0 18px; }"
    css = """    .readiness-panel { border:1px solid #33435b; border-radius:14px; background:#151c28e8; padding:14px; margin:0 0 18px; box-shadow:0 10px 28px #0004; }
    .readiness-panel p { color:#aeb8cc; margin:8px 0 12px; }
    .readiness-status { font-size:12px; padding:4px 8px; border-radius:999px; background:#303846; text-transform:uppercase; letter-spacing:.04em; }
    .readiness-status.ready { background:#124d31; color:#adffd2; }
    .readiness-status.blocked, .readiness-status.unreachable, .readiness-status.stopped { background:#4d3112; color:#ffd8ad; }
    .readiness-status.starting { background:#274267; color:#c9e2ff; }
    .readiness-status.disabled { background:#352b3f; color:#d7c4ff; }
    .readiness-facts { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:8px; margin:12px 0; }
    .readiness-fact { background:#0d1017; border:1px solid #272e3d; border-radius:10px; padding:9px 10px; }
    .readiness-fact span { display:block; color:#91a4c2; font-size:11px; text-transform:uppercase; letter-spacing:.04em; margin-bottom:3px; }
    .readiness-detail { color:#c9d4e8; font-size:13px; white-space:pre-wrap; }
"""
    if css_marker not in source:
        raise RuntimeError("launcher CSS insertion point was not found")
    source = source.replace(css_marker, css + css_marker, 1)

    panel_marker = '  <div id="services" class="grid"></div>'
    panel = """  <section id="kyutai-readiness-panel" class="readiness-panel">
    <div class="row">
      <h2>Kyutai readiness</h2>
      <span id="kyutai-readiness-status" class="readiness-status starting">Checking</span>
    </div>
    <p id="kyutai-readiness-message">Checking moshi-server, adapter, model warmth, and authority eligibility…</p>
    <div class="readiness-facts">
      <div class="readiness-fact"><span>Moshi</span><strong id="kyutai-moshi-state">Checking</strong></div>
      <div class="readiness-fact"><span>Adapter</span><strong id="kyutai-adapter-state">Checking</strong></div>
      <div class="readiness-fact"><span>Upstream</span><strong id="kyutai-upstream-state">Checking</strong></div>
      <div class="readiness-fact"><span>Model</span><strong id="kyutai-model-state">Checking</strong></div>
      <div class="readiness-fact"><span>Authority</span><strong id="kyutai-authority-state">Checking</strong></div>
      <div class="readiness-fact"><span>Failure</span><strong id="kyutai-failure-state">None</strong></div>
    </div>
    <div style="margin:10px 0">
      <button id="probe-kyutai" type="button">Probe now</button>
      <button id="restart-kyutai" type="button">Restart Kyutai stack</button>
      <button id="copy-kyutai-diagnostics" class="copy" type="button">Copy diagnostics</button>
    </div>
    <div id="kyutai-readiness-detail" class="readiness-detail">Waiting for the first readiness result.</div>
  </section>
"""
    if panel_marker not in source:
        raise RuntimeError("launcher readiness-panel insertion point was not found")
    source = source.replace(panel_marker, panel + panel_marker, 1)

    function_marker = "  function captureLogScrollState() {"
    functions = r"""
  let latestKyutaiReadiness = null;
  let kyutaiReadinessBusy = false;

  function setText(id, value) {
    const element = byId(id);
    if (element) element.textContent = String(value ?? '-');
  }

  function renderKyutaiReadiness(status) {
    latestKyutaiReadiness = status || null;
    const state = status && status.state ? status.state : 'unreachable';
    const badge = byId('kyutai-readiness-status');
    if (badge) {
      badge.className = `readiness-status ${state}`;
      badge.textContent = state;
    }
    setText('kyutai-readiness-message', status && status.message ? status.message : 'Unable to read Kyutai readiness.');
    const services = status && status.services ? status.services : {};
    const health = status && status.health ? status.health : {};
    const authority = status && status.authority ? status.authority : {};
    setText('kyutai-moshi-state', services.moshi ? services.moshi.status : 'unknown');
    setText('kyutai-adapter-state', services.adapter ? services.adapter.status : 'unknown');
    setText('kyutai-upstream-state', health.upstream_ready ? 'ready' : 'not ready');
    setText('kyutai-model-state', authority.model_warm ? 'warm' : 'cold');
    setText('kyutai-authority-state', authority.eligible ? 'eligible' : 'blocked');
    const failure = status && status.failure_code
      ? status.failure_code
      : (status && status.adapter_error ? status.adapter_error : 'none');
    setText('kyutai-failure-state', failure);
    const detail = [
      `Language: ${status && status.language ? status.language : '-'}`,
      `Mode: ${status && status.authority_mode ? status.authority_mode : '-'}`,
      `Probe stage: ${health.last_error_stage || '-'}`,
      `Error type: ${health.last_error_type || '-'}`,
      `Circuit: ${health.state || '-'}`,
      `Failures: ${health.failures_in_window ?? '-'} / attempts: ${health.attempts_in_window ?? '-'}`,
      `Retry after: ${health.retry_after_seconds ?? 0}s`
    ];
    setText('kyutai-readiness-detail', detail.join('\n'));
  }

  async function refreshKyutaiReadiness(forceProbe = false) {
    if (kyutaiReadinessBusy) return;
    kyutaiReadinessBusy = true;
    try {
      const status = await api(
        forceProbe
          ? '/api/launcher/kyutai-readiness/probe'
          : '/api/launcher/kyutai-readiness',
        forceProbe ? { method: 'POST' } : undefined
      );
      renderKyutaiReadiness(status);
    } catch (error) {
      renderKyutaiReadiness({
        state: 'unreachable',
        message: error && error.message ? error.message : String(error),
        adapter_error: 'launcher_status_failed'
      });
    } finally {
      kyutaiReadinessBusy = false;
    }
  }

  async function restartKyutaiStack() {
    if (busy) return;
    busy = true;
    showError('');
    try {
      const result = await api('/api/launcher/kyutai-readiness/restart', { method: 'POST' });
      showNotice(result.message || 'Kyutai stack restarted.');
      await refresh();
      await refreshKyutaiReadiness(false);
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    } finally {
      busy = false;
    }
  }

  async function copyKyutaiDiagnostics() {
    if (!latestKyutaiReadiness) {
      await refreshKyutaiReadiness(true);
    }
    const header = `# Omnix Kyutai readiness diagnostics\n# Copied: ${new Date().toISOString()}\n\n`;
    await copyText(header + JSON.stringify(latestKyutaiReadiness || {}, null, 2));
    showNotice('Copied Kyutai readiness diagnostics');
  }

"""
    if function_marker not in source:
        raise RuntimeError("launcher JavaScript function insertion point was not found")
    source = source.replace(function_marker, functions + function_marker, 1)

    listener_marker = "  byId('start-auto').addEventListener('click', () => runAction('/api/services/start-auto'));"
    listeners = """  byId('probe-kyutai').addEventListener('click', () => refreshKyutaiReadiness(true));
  byId('restart-kyutai').addEventListener('click', restartKyutaiStack);
  byId('copy-kyutai-diagnostics').addEventListener('click', copyKyutaiDiagnostics);
"""
    if listener_marker not in source:
        raise RuntimeError("launcher JavaScript listener insertion point was not found")
    source = source.replace(listener_marker, listeners + listener_marker, 1)

    refresh_marker = "  refresh();\n  window.setInterval(refresh, 2000);"
    replacement = """  refreshKyutaiReadiness(false);
  refresh();
  window.setInterval(refresh, 2000);
  window.setInterval(() => refreshKyutaiReadiness(false), 5000);"""
    if refresh_marker not in source:
        raise RuntimeError("launcher refresh insertion point was not found")
    return source.replace(refresh_marker, replacement, 1)