from __future__ import annotations

from typing import Any, Dict, List

from .save_schema import PACKAGE_TYPE
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict


def validate_save_package(package: Dict[str, Any]) -> List[Dict[str, str]]:
    package = dict(package or {})
    errors: List[Dict[str, str]] = []

    if package.get("package_type") != PACKAGE_TYPE:
        errors.append({"field": "package_type", "error": "invalid package type"})

    if not isinstance(package.get("schema_version"), int):
        errors.append({"field": "schema_version", "error": "missing or invalid schema_version"})

    adventure = _safe_dict(package.get("adventure"))
    state = _safe_dict(package.get("state"))

    if not isinstance(adventure.get("setup_payload"), dict):
        errors.append({"field": "adventure.setup_payload", "error": "missing or invalid setup_payload"})

    if not isinstance(state.get("simulation_state"), dict):
        errors.append({"field": "state.simulation_state", "error": "missing or invalid simulation_state"})

    campaign = package.get("campaign")
    if campaign is not None:
        document = _safe_dict(campaign).get("document") if isinstance(campaign, dict) else None
        if not isinstance(campaign, dict) or (document is not None and not isinstance(document, dict)):
            errors.append({"field": "campaign", "error": "invalid campaign document"})
        elif isinstance(document, dict) and not isinstance(document.get("manifest"), dict):
            errors.append({"field": "campaign.document.manifest", "error": "missing campaign manifest"})

    return errors