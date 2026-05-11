from __future__ import annotations

from typing import Any, Dict

DEFAULT_GROUNDING_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "primary_validation": True,
    "llm_safe_fallback_candidate": True,
    "deterministic_fallback": True,
    "background_soft_audit": True,
    "background_soft_audit_mode": "append_correction",
    "background_soft_audit_can_update_state": False,
    "background_soft_audit_validate_correction": True,
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def normalize_grounding_settings(value: Any) -> Dict[str, Any]:
    raw = _safe_dict(value)
    result = dict(DEFAULT_GROUNDING_SETTINGS)

    for key in (
        "enabled",
        "primary_validation",
        "llm_safe_fallback_candidate",
        "deterministic_fallback",
        "background_soft_audit",
        "background_soft_audit_can_update_state",
        "background_soft_audit_validate_correction",
    ):
        if key in raw:
            result[key] = bool(raw.get(key))

    mode = _safe_str(raw.get("background_soft_audit_mode")).strip().lower()
    if mode in {"append_correction", "disabled"}:
        result["background_soft_audit_mode"] = mode

    result["background_soft_audit_can_update_state"] = False
    result["enabled"] = True
    result["primary_validation"] = True
    result["deterministic_fallback"] = True

    return result