from __future__ import annotations

from typing import Any, Dict

from .migration_manager import migrate_package_to_current
from .package_validator import validate_save_package
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict


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
