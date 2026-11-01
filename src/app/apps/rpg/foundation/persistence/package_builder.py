from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .save_schema import (
    CURRENT_RPG_SCHEMA_VERSION,
    ENGINE_VERSION,
    PACKAGE_TYPE,
)
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_save_package(setup_payload: Dict[str, Any], now: str | None = None) -> Dict[str, Any]:
    setup_payload = dict(setup_payload or {})
    metadata = _safe_dict(setup_payload.get("metadata"))
    simulation_state = _safe_dict(metadata.get("simulation_state"))

    # Remove simulation_state from metadata to avoid duplication
    metadata = dict(metadata)
    metadata.pop("simulation_state", None)

    ts = now or _utc_now()

    return {
        "package_type": PACKAGE_TYPE,
        "schema_version": CURRENT_RPG_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "created_at": ts,
        "updated_at": ts,
        "adventure": {
            "setup_payload": setup_payload,
            "metadata": metadata,
        },
        "state": {
            "simulation_state": simulation_state,
        },
        "artifacts": {
            "snapshots": list(simulation_state.get("snapshots") or []),
            "timeline": dict(simulation_state.get("timeline") or {}),
        },
        "campaign": {"document_version": None, "document": None},
    }


def build_campaign_save_package(document: Dict[str, Any], now: str | None = None) -> Dict[str, Any]:
    """A package (format 8) carrying a whole campaign document, with its setup and simulation as before."""
    document = dict(document or {})
    setup_payload = dict(_safe_dict(document.get("setup_payload")))
    metadata = dict(_safe_dict(setup_payload.get("metadata")))
    metadata["simulation_state"] = _safe_dict(document.get("simulation_state"))
    setup_payload["metadata"] = metadata
    package = build_save_package(setup_payload, now=now)
    version = _safe_dict(document.get("manifest")).get("schema_version")
    package["campaign"] = {"document_version": version, "document": document}
    return package
