from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.launcher.huggingface_token_store import (
    clear_huggingface_token,
    huggingface_token_status,
    save_huggingface_token,
)
from app.launcher.service_manager import get_default_manager

_ROUTE_SENTINEL = "_omnix_huggingface_token_controls_registered"
_MODEL_CACHE_DIRECTORY = "models--kyutai--stt-1b-en_fr-candle"


class HuggingFaceTokenRequest(BaseModel):
    token: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _model_cache_path() -> Path:
    root = _repo_root()
    unmute_dir = Path(
        os.environ.get("KYUTAI_UNMUTE_DIR", str(root.parent / "unmute"))
    ).expanduser()
    return unmute_dir / "volumes" / "hf-cache" / "hub" / _MODEL_CACHE_DIRECTORY


def _public_status() -> dict[str, Any]:
    token = huggingface_token_status(_repo_root())
    return {
        "configured": bool(token["configured"]),
        "source": token["source"],
        "model_cached": _model_cache_path().is_dir(),
    }


def _restart_moshi() -> dict[str, Any]:
    manager = get_default_manager()
    try:
        return manager.restart("kyutai_moshi")
    except KeyError as exc:
        raise HTTPException(
            status_code=409,
            detail="Kyutai moshi-server is not registered in this launcher.",
        ) from exc


def register_huggingface_token_controls(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/launcher/hugging-face-token")
    def get_huggingface_token_status() -> dict[str, Any]:
        return _public_status()

    @app.put("/api/launcher/hugging-face-token")
    def put_huggingface_token(request: HuggingFaceTokenRequest) -> dict[str, Any]:
        try:
            save_huggingface_token(request.token, _repo_root())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        service_action = _restart_moshi()
        status = _public_status()
        return {
            **status,
            "ok": bool(service_action.get("ok")),
            "service_action": service_action,
            "message": (
                "Token saved locally. Kyutai moshi-server was restarted; "
                "the model will download automatically if it is not already cached."
            ),
        }

    @app.delete("/api/launcher/hugging-face-token")
    def delete_huggingface_token() -> dict[str, Any]:
        clear_huggingface_token(_repo_root())
        manager = get_default_manager()
        try:
            service_action = manager.stop("kyutai_moshi")
        except KeyError:
            service_action = {"ok": True, "already_stopped": True}
        return {
            **_public_status(),
            "ok": True,
            "service_action": service_action,
            "message": "Saved token cleared and Kyutai moshi-server stopped.",
        }


def enhance_launcher_html(source: str) -> str:
    if 'id="hf-token-panel"' in source:
        return source

    css_marker = "    .toolbar { margin: 12px 0 18px; }"
    css = """    .secret-panel { border:1px solid #33435b; border-radius:14px; background:#151c28e8; padding:14px; margin:0 0 18px; box-shadow:0 10px 28px #0004; }
    .secret-panel p { color:#aeb8cc; margin:8px 0 12px; }
    .secret-form { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
    .secret-form input { flex:1 1 320px; min-width:220px; border:1px solid #3a465c; border-radius:10px; padding:10px 12px; background:#0d1017; color:#eef2ff; font:inherit; }
    .secret-form input:focus { outline:2px solid #5f8ed8; outline-offset:1px; }
    .secret-detail { color:#91a4c2; font-size:12px; margin-top:8px; }
    .secret-status { font-size:12px; padding:4px 8px; border-radius:999px; background:#4d3112; color:#ffd8ad; text-transform:uppercase; letter-spacing:.04em; }
    .secret-status.configured { background:#124d31; color:#adffd2; }
    .secret-status.busy { background:#274267; color:#c9e2ff; }
"""
    if css_marker not in source:
        raise RuntimeError("launcher CSS insertion point was not found")
    source = source.replace(css_marker, css + css_marker, 1)

    panel_marker = '  <div id="services" class="grid"></div>'
    panel = """  <section id="hf-token-panel" class="secret-panel">
    <div class="row">
      <h2>Hugging Face access token</h2>
      <span id="hf-token-status" class="secret-status">Checking</span>
    </div>
    <p>Used only by the local Kyutai moshi-server to download the STT model. The token is masked, never shown in logs, and saved under ignored local runtime data.</p>
    <div class="secret-form">
      <input id="hf-token-input" type="password" placeholder="hf_..." autocomplete="new-password" spellcheck="false" aria-label="Hugging Face access token" />
      <button id="save-hf-token" type="button">Save token &amp; start download</button>
      <button id="clear-hf-token" class="stop" type="button">Clear token</button>
    </div>
    <div id="hf-token-detail" class="secret-detail">Checking local configuration…</div>
  </section>
"""
    if panel_marker not in source:
        raise RuntimeError("launcher token-panel insertion point was not found")
    source = source.replace(panel_marker, panel + panel_marker, 1)

    function_marker = "  function captureLogScrollState() {"
    functions = r"""
  function setHuggingFaceTokenStatus(status) {
    const badge = byId('hf-token-status');
    const detail = byId('hf-token-detail');
    if (!badge || !detail) return;
    const configured = Boolean(status && status.configured);
    badge.className = `secret-status ${configured ? 'configured' : ''}`;
    badge.textContent = configured ? 'Configured' : 'Not configured';
    if (!configured) {
      detail.textContent = 'Enter a Hugging Face token to start or restart Kyutai and download the model.';
      return;
    }
    const sourceLabel = status.source === 'local_file'
      ? 'Saved on this machine'
      : 'Available from the launcher environment';
    const cacheLabel = status.model_cached
      ? 'Model cache detected; an existing download will be reused.'
      : 'Model is not cached yet; saving will start the download.';
    detail.textContent = `${sourceLabel}. ${cacheLabel}`;
  }

  async function refreshHuggingFaceTokenStatus() {
    try {
      const status = await api('/api/launcher/hugging-face-token');
      setHuggingFaceTokenStatus(status);
    } catch (error) {
      const detail = byId('hf-token-detail');
      if (detail) detail.textContent = 'Unable to read Hugging Face token status.';
    }
  }

  async function saveHuggingFaceToken() {
    if (busy) return;
    const input = byId('hf-token-input');
    const token = input ? input.value.trim() : '';
    if (!token) {
      showError('Enter a Hugging Face access token first.');
      return;
    }
    busy = true;
    showError('');
    const badge = byId('hf-token-status');
    if (badge) {
      badge.className = 'secret-status busy';
      badge.textContent = 'Saving';
    }
    try {
      const result = await api('/api/launcher/hugging-face-token', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
      });
      if (input) input.value = '';
      setHuggingFaceTokenStatus(result);
      showNotice(result.message || 'Token saved; Kyutai download started.');
      await refresh();
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
      await refreshHuggingFaceTokenStatus();
    } finally {
      busy = false;
    }
  }

  async function clearHuggingFaceToken() {
    if (busy) return;
    if (!window.confirm('Clear the saved Hugging Face token and stop Kyutai moshi-server?')) return;
    busy = true;
    showError('');
    try {
      const result = await api('/api/launcher/hugging-face-token', { method: 'DELETE' });
      const input = byId('hf-token-input');
      if (input) input.value = '';
      setHuggingFaceTokenStatus(result);
      showNotice(result.message || 'Token cleared.');
      await refresh();
    } catch (error) {
      showError(error && error.message ? error.message : String(error));
    } finally {
      busy = false;
    }
  }

"""
    if function_marker not in source:
        raise RuntimeError("launcher JavaScript function insertion point was not found")
    source = source.replace(function_marker, functions + function_marker, 1)

    listener_marker = "  byId('start-auto').addEventListener('click', () => runAction('/api/services/start-auto'));"
    listeners = """  byId('save-hf-token').addEventListener('click', saveHuggingFaceToken);
  byId('clear-hf-token').addEventListener('click', clearHuggingFaceToken);
  byId('hf-token-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') saveHuggingFaceToken();
  });
"""
    if listener_marker not in source:
        raise RuntimeError("launcher JavaScript listener insertion point was not found")
    source = source.replace(listener_marker, listeners + listener_marker, 1)

    refresh_marker = "  refresh();\n  window.setInterval(refresh, 2000);"
    replacement = """  refreshHuggingFaceTokenStatus();
  refresh();
  window.setInterval(refresh, 2000);
  window.setInterval(refreshHuggingFaceTokenStatus, 5000);"""
    if refresh_marker not in source:
        raise RuntimeError("launcher refresh insertion point was not found")
    return source.replace(refresh_marker, replacement, 1)
