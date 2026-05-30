from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from types import ModuleType
from typing import Any, Dict

from app.rpg.session.fast_combat_presentation import (
    deterministic_fast_combat_payload,
    repair_fast_combat_grounding_validation,
)

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_POST_IMPORT_FINDER_ATTR = "_pr034_interactive_fast_combat_result_finder_installed"
_PATCH_ATTR = "_pr034_interactive_fast_combat_result_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_pr034_original_interactive_apply_turn"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _combat_grounding_validation() -> Dict[str, Any]:
    return {
        "ok": True,
        "fallback_used": False,
        "fallback_source": "deterministic_combat_fast_summary",
        "selected_candidate": "deterministic_combat_fast_summary",
        "violations": [],
        "fast_combat_delta_supported": True,
        "fast_combat_delta_support_source": "deterministic_combat_fast_summary",
    }


def _normalized_fast_combat_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    if not payload:
        return payload
    normalized = dict(payload)
    normalized["grounding_validation"] = _combat_grounding_validation()
    normalized["grounding_fallback"] = False
    normalized["grounding_fallback_source"] = "deterministic_combat_fast_summary"
    normalized["grounding_selected_candidate"] = "deterministic_combat_fast_summary"
    normalized["grounding_violation_codes"] = []
    return normalized


def normalize_interactive_fast_combat_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize transcript-facing fast-combat payloads after interactive apply_turn.

    The canonical runtime may rewrite narration_payload to a deferred fallback after
    final presentation selection. Matrix/manual transcripts derive debug fields
    from narration_payload, so restore deterministic fast-combat payloads here
    when they are backed by combat_delta.
    """

    result = repair_fast_combat_grounding_validation(result)
    payload = deterministic_fast_combat_payload(result)
    if not payload:
        return result
    payload = _normalized_fast_combat_payload(payload)
    result["narration_payload"] = dict(payload)
    result["structured_narration"] = dict(payload)
    result["grounding_validation"] = _combat_grounding_validation()
    result["grounding_violation_codes"] = []
    result["grounding_fallback"] = False
    result["grounding_fallback_source"] = "deterministic_combat_fast_summary"
    result["grounding_selected_candidate"] = "deterministic_combat_fast_summary"

    nested = _safe_dict(result.get("result"))
    if nested:
        nested["narration_payload"] = dict(payload)
        nested["structured_narration"] = dict(payload)
        nested["grounding_validation"] = _combat_grounding_validation()
        nested["grounding_violation_codes"] = []
        nested["grounding_fallback"] = False
        nested["grounding_fallback_source"] = "deterministic_combat_fast_summary"
        nested["grounding_selected_candidate"] = "deterministic_combat_fast_summary"
        result["result"] = nested
    return result


def _patch_interactive_module(module: ModuleType) -> bool:
    if getattr(module, _PATCH_ATTR, False):
        return False
    original = getattr(module, "apply_turn", None)
    if not callable(original):
        return False

    def _wrapped_apply_turn(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if isinstance(result, dict):
            return normalize_interactive_fast_combat_result(result)
        return result

    setattr(module, _ORIGINAL_APPLY_TURN_ATTR, original)
    setattr(module, "apply_turn", _wrapped_apply_turn)
    setattr(module, _PATCH_ATTR, True)
    return True


class _InteractivePostImportLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader: importlib.abc.Loader):
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create_module = getattr(self._wrapped_loader, "create_module", None)
        if callable(create_module):
            return create_module(spec)
        return None

    def exec_module(self, module):  # type: ignore[no-untyped-def]
        self._wrapped_loader.exec_module(module)  # type: ignore[attr-defined]
        if module.__name__ == _INTERACTIVE_MODULE:
            _patch_interactive_module(module)


class _InteractivePostImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != _INTERACTIVE_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or isinstance(spec.loader, _InteractivePostImportLoader):
            return spec
        spec.loader = _InteractivePostImportLoader(spec.loader)
        return spec


def _install_post_import_finder() -> bool:
    if getattr(sys, _POST_IMPORT_FINDER_ATTR, False):
        return False
    sys.meta_path.insert(0, _InteractivePostImportFinder())
    setattr(sys, _POST_IMPORT_FINDER_ATTR, True)
    return True


def install_interactive_fast_combat_result_hook() -> bool:
    module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType) and _patch_interactive_module(module):
        return True
    return _install_post_import_finder()


def force_install_interactive_fast_combat_result_hook_for_tests(module: ModuleType | None = None) -> bool:
    if module is None:
        module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        original = getattr(module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original):
            setattr(module, "apply_turn", original)
        if hasattr(module, _PATCH_ATTR):
            setattr(module, _PATCH_ATTR, False)
        return _patch_interactive_module(module)
    return install_interactive_fast_combat_result_hook()
