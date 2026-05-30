from __future__ import annotations

from typing import Any, Dict

_FAST_DIRECT_SOURCES = {
    "ce211_fast_direct_runtime_budget_v1",
    "ce212_fast_direct_runtime_budget_v1",
}
_PATCH_ATTR = "_ce212_fast_combat_narration_skip_installed"
_ORIGINAL_ATTR = "_ce212_original_apply_combat_narration_if_needed"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _contains_fast_direct_marker(value: Any, *, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, dict):
        source = _safe_str(value.get("source") or value.get("fast_direct_source"))
        if source in _FAST_DIRECT_SOURCES:
            return True
        if value.get("fast_direct_runtime") is True or value.get("skip_sync_combat_narration") is True:
            return True
        metadata = value.get("metadata")
        if isinstance(metadata, dict) and _contains_fast_direct_marker(metadata, depth=depth + 1):
            return True
        for key in (
            "turn_contract",
            "action",
            "first_call_action_advisory",
            "first_call_grounding_diagnostics",
            "turn_grounding_packet",
            "fast_direct_action",
            "semantic_action",
        ):
            if key in value and _contains_fast_direct_marker(value.get(key), depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_contains_fast_direct_marker(item, depth=depth + 1) for item in value[:20])
    return False


def _should_skip(payload: Dict[str, Any], combat_state: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    combat_state = _safe_dict(combat_state)
    if payload.get("skip_sync_combat_narration") or payload.get("fast_direct_runtime"):
        return True
    if combat_state.get("skip_sync_combat_narration") or combat_state.get("fast_direct_runtime"):
        return True
    if _safe_str(payload.get("fast_direct_source")) in _FAST_DIRECT_SOURCES:
        return True
    if _safe_str(combat_state.get("fast_direct_source")) in _FAST_DIRECT_SOURCES:
        return True
    return _contains_fast_direct_marker(payload) or _contains_fast_direct_marker(combat_state)


def _fallback_summary(combat_result: Dict[str, Any]) -> str:
    combat_result = _safe_dict(combat_result)
    for key in ("summary", "result", "outcome", "reason", "action_type"):
        text = _safe_str(combat_result.get(key)).strip()
        if text:
            return f"Result: {text}"
    return "Result: combat_action_resolved"


def _build_contract(runtime_module: Any, combat_result: Dict[str, Any], combat_state: Dict[str, Any]) -> Dict[str, Any]:
    builder = getattr(runtime_module, "build_combat_narration_contract", None)
    if callable(builder):
        try:
            return _safe_dict(builder(combat_result=combat_result, combat_state=combat_state))
        except Exception:
            return {}
    return {}


def _apply_fast_skip(
    runtime_module: Any,
    payload: Dict[str, Any],
    *,
    combat_result: Dict[str, Any],
    combat_state: Dict[str, Any],
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)
    narration = _fallback_summary(combat_result)

    payload["combat_narration_attempted"] = False
    payload["combat_narration_skipped_for_fast_mode"] = True
    payload["combat_narration_skip_source"] = "ce212_fast_combat_narration_skip_v1"
    payload["llm_called"] = False
    payload["llm_purpose"] = "deterministic_combat_fast_summary"
    payload["combat_narration_error"] = ""
    payload["combat_narration_contract"] = _build_contract(runtime_module, combat_result, combat_state)
    payload["combat_narration_validation"] = {
        "ok": False,
        "warnings": ["combat_narration_skipped_for_fast_mode"],
        "source": "ce212_fast_combat_narration_skip_v1",
    }
    payload["combat_narration_payload"] = {
        "source": "deterministic_combat_fast_summary",
        "narration": narration,
        "npc": {},
    }
    payload["combat_narration_accepted"] = False
    payload["combat_narration_rejected"] = False

    for key in ("narration", "final_narration", "narration_preview", "raw_payload_narration"):
        if not _safe_str(payload.get(key)).strip():
            payload[key] = narration
    nested = _safe_dict(payload.get("result"))
    if nested:
        nested["combat_narration_skipped_for_fast_mode"] = True
        nested["combat_narration_skip_source"] = "ce212_fast_combat_narration_skip_v1"
        payload["result"] = nested
    return payload


def install_fast_combat_narration_skip() -> bool:
    """Install a narrow runtime hook that skips blocking combat LLM narration in fast-direct mode."""
    from app.rpg.session import runtime as runtime_module

    if getattr(runtime_module, _PATCH_ATTR, False):
        return False

    original = getattr(runtime_module, "_apply_combat_narration_if_needed", None)
    if not callable(original):
        return False

    def _wrapped_apply_combat_narration_if_needed(
        payload: Dict[str, Any],
        *,
        combat_result: Dict[str, Any],
        combat_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if _should_skip(_safe_dict(payload), _safe_dict(combat_state)):
            return _apply_fast_skip(
                runtime_module,
                payload,
                combat_result=combat_result,
                combat_state=combat_state,
            )
        return original(payload, combat_result=combat_result, combat_state=combat_state)

    setattr(runtime_module, _ORIGINAL_ATTR, original)
    setattr(runtime_module, "_apply_combat_narration_if_needed", _wrapped_apply_combat_narration_if_needed)
    setattr(runtime_module, _PATCH_ATTR, True)
    return True


# Keep a direct callable for tests and explicit reinstallation.
def force_install_fast_combat_narration_skip_for_tests() -> bool:
    from app.rpg.session import runtime as runtime_module

    original = getattr(runtime_module, _ORIGINAL_ATTR, None)
    if callable(original):
        setattr(runtime_module, "_apply_combat_narration_if_needed", original)
    if hasattr(runtime_module, _PATCH_ATTR):
        setattr(runtime_module, _PATCH_ATTR, False)
    return install_fast_combat_narration_skip()
