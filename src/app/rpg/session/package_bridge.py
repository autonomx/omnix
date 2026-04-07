"""Phase 15.1 — Session/package bridge (canonical).

Provides deterministic, schema-preserving conversion between session
and portable package formats. Includes import traceability metadata.
"""
from __future__ import annotations

from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def session_to_package(session: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a session dict to a portable package dict.

    Preserves schema version, installed packs, memory and presentation state.
    """
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    return {
        "package_manifest": {
            "source_session_id": manifest.get("id"),
            "title": manifest.get("title"),
            "schema_version": manifest.get("schema_version", 2),
            "package_kind": "rpg_session_export",
        },
        "session_manifest": manifest,
        "simulation_state": simulation_state,
        "installed_packs": session.get("installed_packs", []),
    }


def package_to_session(package_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a portable package dict back to a session dict.

    Ensures manifest has a schema_version and preserves import metadata
    for auditability.
    """
    package_payload = _safe_dict(package_payload)
    session_manifest = _safe_dict(package_payload.get("session_manifest"))
    simulation_state = _safe_dict(package_payload.get("simulation_state"))
    session_manifest.setdefault("schema_version", 2)
    return {
        "manifest": session_manifest,
        "simulation_state": simulation_state,
        "installed_packs": package_payload.get("installed_packs", []),
        "import_metadata": {
            "package_manifest": _safe_dict(package_payload.get("package_manifest")),
        },
    }