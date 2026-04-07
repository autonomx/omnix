"""Phase 15.1 — Session ↔ Package Unification.

Let sessions export/import through the same package layer:
- package = portable serialized export
- session = live resumable play state
- Preserve installed content packs in package/session conversions
- Session metadata linked to package manifest
"""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.packaging.package_io import export_session_package, import_session_package


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def session_to_package(session: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a session snapshot to a portable package export."""
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    state = _safe_dict(session.get("state"))

    return export_session_package(
        state,
        title=manifest.get("title", "") or "Session Package",
        description="Exported from session",
        created_by="session_bridge",
    )


def package_to_session(package_data: Dict[str, Any], *, session_id: str, title: str) -> Dict[str, Any]:
    """Convert a portable package back into a resumable session."""
    imported = import_session_package(_safe_dict(package_data))
    simulation_state = _safe_dict(imported.get("simulation_state"))
    return {
        "manifest": {
            "id": session_id,
            "title": title,
            "status": "active",
            "created_at": "",
            "updated_at": "",
            "source_pack_id": "",
            "source_template_id": "",
        },
        "state": simulation_state,
    }