from __future__ import annotations

from types import ModuleType
from typing import Any, Dict

from app.rpg.session.fast_combat_presentation import deterministic_fast_combat_payload

_PATCH_ATTR = "_pr02_fast_combat_presentation_hook_installed"
_ORIGINAL_SELECTOR_ATTR = "_pr02_original_select_final_visible_presentation"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _fast_combat_selection(
    final_result: Dict[str, Any],
    *,
    runtime_narration_payload: Dict[str, Any],
) -> Dict[str, Any]:
    payload = deterministic_fast_combat_payload(final_result)
    narration = _safe_str(payload.get("narration")).strip()
    if not narration:
        return {}
    return {
        "source": "deterministic_combat_fast_summary",
        "narration": narration,
        "npc": _safe_dict(payload.get("npc")),
        "llm_called": False,
        "runtime_payload_source": _safe_str(_safe_dict(runtime_narration_payload).get("source")),
        "combat_delta": _safe_dict(payload.get("combat_delta") or payload.get("combat_delta_contract")),
    }


def install_fast_combat_presentation_hook(runtime_module: ModuleType | None = None) -> bool:
    """Promote deterministic fast combat summaries during final presentation selection.

    Provider combat narration still requires validation ok=True in runtime. Fast
    combat is different: provider narration is intentionally skipped, but the
    deterministic payload is backed by a combat delta. This hook lets that backed
    deterministic payload win over stale deferred fallback text.
    """

    if runtime_module is None:
        from app.rpg.session import runtime as runtime_module  # type: ignore[no-redef]

    if getattr(runtime_module, _PATCH_ATTR, False):
        return False

    original = getattr(runtime_module, "_select_final_visible_presentation", None)
    if not callable(original):
        return False

    def _wrapped_select_final_visible_presentation(
        final_result: Dict[str, Any],
        *,
        runtime_narration_payload: Dict[str, Any],
        prior_narration: str,
        prior_npc: Dict[str, Any],
        prior_llm_called: bool,
    ) -> Dict[str, Any]:
        fast_combat = _fast_combat_selection(
            final_result,
            runtime_narration_payload=runtime_narration_payload,
        )
        if fast_combat:
            return fast_combat
        return original(
            final_result,
            runtime_narration_payload=runtime_narration_payload,
            prior_narration=prior_narration,
            prior_npc=prior_npc,
            prior_llm_called=prior_llm_called,
        )

    setattr(runtime_module, _ORIGINAL_SELECTOR_ATTR, original)
    setattr(runtime_module, "_select_final_visible_presentation", _wrapped_select_final_visible_presentation)
    setattr(runtime_module, _PATCH_ATTR, True)
    return True


def force_install_fast_combat_presentation_hook_for_tests(runtime_module: ModuleType | None = None) -> bool:
    if runtime_module is None:
        from app.rpg.session import runtime as runtime_module  # type: ignore[no-redef]

    original = getattr(runtime_module, _ORIGINAL_SELECTOR_ATTR, None)
    if callable(original):
        setattr(runtime_module, "_select_final_visible_presentation", original)
    if hasattr(runtime_module, _PATCH_ATTR):
        setattr(runtime_module, _PATCH_ATTR, False)
    return install_fast_combat_presentation_hook(runtime_module)
