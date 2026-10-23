from __future__ import annotations

from typing import Any, Dict

from .migration_manager import migrate_package_to_current
from .package_validator import validate_save_package
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict


def load_save_package(package: Dict[str, Any]) -> Dict[str, Any]:
    package = migrate_package_to_current(dict(package or {}))
    errors = validate_save_package(package)
    if errors:
        raise ValueError(f"Invalid RPG save package: {errors}")

    adventure = _safe_dict(package.get("adventure"))
    setup_payload = _safe_dict(adventure.get("setup_payload"))
    state = _safe_dict(package.get("state"))
    simulation_state = _safe_dict(state.get("simulation_state"))

    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata

    simulation_state.setdefault("save_meta", {})
    simulation_state["save_meta"]["schema_version"] = package.get("schema_version")

    return setup_payload


def campaign_document_from_package(package: Dict[str, Any]) -> Dict[str, Any] | None:
    """The campaign document a package carries (format 8), as stored in it; None when it carries none.

    ``campaign_state.load_campaign_save_package`` loads it in the current document shape.
    """
    package = migrate_package_to_current(dict(package or {}))
    errors = validate_save_package(package)
    if errors:
        raise ValueError(f"Invalid RPG save package: {errors}")
    document = _safe_dict(package.get("campaign")).get("document")
    return dict(document) if isinstance(document, dict) else None
