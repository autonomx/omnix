from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.base import _extract_nested_dict_by_key, _first_dict
from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str


def _extract_npc_backbone_decision(turn_summary: Dict[str, Any]) -> Dict[str, Any]:
    return _first_dict(
        turn_summary.get("npc_backbone_decision"),
        _safe_dict(turn_summary.get("resolved_result")).get("npc_backbone_decision"),
        _safe_dict(turn_summary.get("result")).get("npc_backbone_decision"),
        _extract_nested_dict_by_key(turn_summary, "npc_backbone_decision"),
    )


def _extract_narration_quality_warnings(turn_summary: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    warnings.extend(_safe_list(turn_summary.get("narration_quality_warnings")))
    warnings.extend(_safe_list(_safe_dict(turn_summary.get("resolved_result")).get("narration_quality_warnings")))
    warnings.extend(_safe_list(_safe_dict(turn_summary.get("result")).get("narration_quality_warnings")))
    return list(dict.fromkeys([_safe_str(x) for x in warnings if _safe_str(x)]))


def _runtime_has_narration_quality_memory(turn_summary: Dict[str, Any]) -> bool:
    context = _safe_dict(
        turn_summary.get("narration_quality_context")
        or _safe_dict(turn_summary.get("resolved_result")).get("narration_quality_context")
        or _safe_dict(turn_summary.get("result")).get("narration_quality_context")
    )
    if (
        _safe_list(context.get("recent_openings"))
        or _safe_list(context.get("recent_fingerprints"))
        or _safe_list(context.get("recent_generic_phrases"))
    ):
        return True

    def has_quality(value: Any, depth: int = 0) -> bool:
        if depth > 8:
            return False
        if isinstance(value, dict):
            quality = _safe_dict(value.get("narration_quality"))
            if (
                _safe_list(quality.get("recent_openings"))
                or _safe_list(quality.get("recent_fingerprints"))
                or _safe_list(quality.get("recent_generic_phrases"))
            ):
                return True
            for nested in value.values():
                if has_quality(nested, depth + 1):
                    return True
        elif isinstance(value, list):
            for nested in value:
                if has_quality(nested, depth + 1):
                    return True
        return False

    return has_quality(turn_summary)