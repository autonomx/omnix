from __future__ import annotations

from functools import wraps
from types import ModuleType
from typing import Any

from app.rpg.session.turn_memory_runtime_attach import attach_turn_memory_to_runtime_result
from app.rpg.session.turn_memory_runtime_persistence import extract_call_context

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_PATCH_ATTR = "_phase1433_turn_memory_runtime_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_phase1433_original_interactive_apply_turn"


def patch_interactive_module(module: ModuleType) -> bool:
    if getattr(module, _PATCH_ATTR, False):
        return False
    original = getattr(module, "apply_turn", None)
    if not callable(original):
        return False

    @wraps(original)
    def _wrapped_apply_turn(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if isinstance(result, dict):
            return attach_turn_memory_to_runtime_result(result, call_context=extract_call_context(args, kwargs))
        return result

    _wrapped_apply_turn.__module__ = getattr(original, "__module__", _INTERACTIVE_MODULE)
    _wrapped_apply_turn.__name__ = getattr(original, "__name__", "apply_turn")
    _wrapped_apply_turn.__qualname__ = getattr(original, "__qualname__", "apply_turn")
    setattr(module, _ORIGINAL_APPLY_TURN_ATTR, original)
    setattr(module, "apply_turn", _wrapped_apply_turn)
    setattr(module, _PATCH_ATTR, True)
    return True
