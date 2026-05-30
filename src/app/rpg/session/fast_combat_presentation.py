from __future__ import annotations

from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _candidate_payloads(result: Dict[str, Any]) -> list[Dict[str, Any]]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    resolved = _safe_dict(result.get("resolved_result")) or _safe_dict(nested.get("resolved_result"))
    return [
        _safe_dict(result.get("combat_narration_payload")),
        _safe_dict(nested.get("combat_narration_payload")),
        _safe_dict(resolved.get("combat_narration_payload")),
        _safe_dict(result.get("structured_narration")),
        _safe_dict(nested.get("structured_narration")),
        _safe_dict(resolved.get("structured_narration")),
        _safe_dict(result.get("narration_payload")),
        _safe_dict(nested.get("narration_payload")),
        _safe_dict(resolved.get("narration_payload")),
    ]


def _has_valid_combat_delta(payload: Dict[str, Any]) -> bool:
    delta = _safe_dict(payload.get("combat_delta")) or _safe_dict(payload.get("combat_delta_contract"))
    if not delta:
        return False
    if delta.get("damage_applied") not in (None, ""):
        return True
    if delta.get("defeated") is True or delta.get("combat_ended") is True:
        return True
    if delta.get("target_hp_before") not in (None, "") and delta.get("target_hp_after") not in (None, ""):
        return True
    return False


def deterministic_fast_combat_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return deterministic fast-combat presentation when backed by combat delta.

    Fast combat deliberately skips provider narration, so its validation payload is
    not an accepted provider combat narration. This helper lets report/UI
    presentation still prefer the deterministic combat summary when it carries a
    backed combat delta, preventing stale deferred fallback text from hiding real
    damage.
    """

    for payload in _candidate_payloads(result):
        if _safe_str(payload.get("source")) != "deterministic_combat_fast_summary":
            continue
        narration = _safe_str(payload.get("narration")).strip()
        if narration and _has_valid_combat_delta(payload):
            return payload
    return {}


def prefer_fast_combat_narration(result: Dict[str, Any], fallback: Any = "") -> str:
    payload = deterministic_fast_combat_payload(result)
    narration = _safe_str(payload.get("narration")).strip()
    if narration:
        return narration
    return _safe_str(fallback).strip()
