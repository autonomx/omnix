"""Phase 13.5 — Session lifecycle + persistence module.

Provides bounded, normalized session registry management.
"""
from __future__ import annotations

from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _normalize_session(value: Any) -> Dict[str, Any]:
    """Normalize a session record while preserving durable manifest counters."""

    data = _safe_dict(value)
    manifest = _safe_dict(data.get("manifest"))
    state = _safe_dict(data.get("state"))
    normalized_manifest = dict(manifest)
    normalized_manifest.update(
        {
            "id": _safe_str(manifest.get("id") or manifest.get("session_id")).strip(),
            "session_id": _safe_str(manifest.get("session_id") or manifest.get("id")).strip(),
            "schema_version": _safe_int(manifest.get("schema_version"), 2),
            "title": _safe_str(manifest.get("title")).strip(),
            "status": _first_non_empty(manifest.get("status"), "active"),
            "created_at": _safe_str(manifest.get("created_at")).strip(),
            "updated_at": _safe_str(manifest.get("updated_at")).strip(),
            "source_pack_id": _safe_str(manifest.get("source_pack_id")).strip(),
            "source_template_id": _safe_str(manifest.get("source_template_id")).strip(),
            "archived": bool(manifest.get("archived")),
        }
    )
    normalized = {
        "manifest": normalized_manifest,
        "state": state,
        "setup_payload": _safe_dict(data.get("setup_payload")),
        "simulation_state": _safe_dict(data.get("simulation_state")),
        "runtime_state": _safe_dict(data.get("runtime_state")),
    }
    from app.apps.rpg.session.public_state_bridge import synchronize_player_projections

    return synchronize_player_projections(normalized)
