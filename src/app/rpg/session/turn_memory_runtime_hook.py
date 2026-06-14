from __future__ import annotations

import sys
from functools import wraps
from types import ModuleType
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, s
from app.rpg.session.turn_memory_contract import attach_turn_memory_context_with_session
from app.rpg.session.turn_memory_runtime_import_hook import install_post_import_finder, preserve_player_agency_hook
from app.rpg.session.turn_memory_runtime_persistence import (
    extract_call_context,
    save_persisted_session,
    select_memory_session,
)
from app.rpg.session.turn_memory_runtime_status import attach_hook_status

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_PATCH_ATTR = "_phase1433_turn_memory_runtime_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_phase1433_original_interactive_apply_turn"


def attach_turn_memory_to_runtime_result(result: dict[str, Any], *, call_context: Mapping[str, Any]) -> dict[str, Any]:
    """Attach deterministic recent/dialogue memory to an interactive turn result."""

    if not isinstance(result, dict):
        return result
    context = d(call_context)
    try:
        session, can_persist = select_memory_session(result, context)
        updated_result, updated_session = attach_turn_memory_context_with_session(
            result,
            session=session,
            player_input=s(context.get("player_input")),
        )
        persisted = save_persisted_session(
            updated_session,
            session_id=s(context.get("session_id")),
        ) if can_persist else False
        return attach_hook_status(updated_result, attached=True, persisted=persisted)
    except Exception as exc:
        return attach_hook_status(result, attached=False, error=f"{type(exc).__name__}: {exc}")


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
            return attach_turn_memory_to_runtime_result(
                result,
                call_context=extract_call_context(args, kwargs),
            )
        return result

    _wrapped_apply_turn.__module__ = getattr(original, "__module__", _INTERACTIVE_MODULE)
    _wrapped_apply_turn.__name__ = getattr(original, "__name__", "apply_turn")
    _wrapped_apply_turn.__qualname__ = getattr(original, "__qualname__", "apply_turn")
    setattr(module, _ORIGINAL_APPLY_TURN_ATTR, original)
    setattr(module, "apply_turn", _wrapped_apply_turn)
    setattr(module, _PATCH_ATTR, True)
    return True


def install_turn_memory_runtime_hook() -> bool:
    module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        preserve_player_agency_hook(module)
        if patch_interactive_module(module):
            return True
    return install_post_import_finder()


def force_install_turn_memory_runtime_hook_for_tests(module: ModuleType | None = None) -> bool:
    if module is None:
        module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        original = getattr(module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original):
            setattr(module, "apply_turn", original)
        if hasattr(module, _PATCH_ATTR):
            setattr(module, _PATCH_ATTR, False)
        return patch_interactive_module(module)
    return install_turn_memory_runtime_hook()
