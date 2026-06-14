from __future__ import annotations

import sys
from copy import deepcopy
from functools import wraps
from types import ModuleType
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, s
from app.rpg.session.turn_memory_contract import attach_turn_memory_context_with_session
from app.rpg.session.turn_memory_runtime_import_hook import install_post_import_finder, preserve_player_agency_hook

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_PATCH_ATTR = "_phase1433_turn_memory_runtime_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_phase1433_original_interactive_apply_turn"
HOOK_FORMAT_VERSION = "phase14_33_turn_memory_runtime_hook_v1"


def _extract_call_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": s(kwargs.get("session_id") if "session_id" in kwargs else (args[0] if len(args) >= 1 else "")),
        "player_input": s(kwargs.get("player_input") if "player_input" in kwargs else (args[1] if len(args) >= 2 else "")),
        "session_override": deepcopy(d(kwargs.get("session_override"))),
    }


def _load_persisted_session(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    try:
        from app.rpg.session import runtime as canonical_runtime

        return d(canonical_runtime.load_runtime_session(session_id))
    except Exception:
        return {}


def _save_persisted_session(session: Mapping[str, Any], *, session_id: str) -> bool:
    if not session_id or not isinstance(session, Mapping):
        return False
    try:
        from app.rpg.session import runtime as canonical_runtime

        session_to_save = deepcopy(d(session))
        manifest = d(session_to_save.get("manifest"))
        manifest.setdefault("session_id", session_id)
        manifest.setdefault("id", session_id)
        session_to_save["manifest"] = manifest
        canonical_runtime.save_runtime_session(session_to_save)
        return True
    except Exception:
        return False


def _select_memory_session(result: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    session_id = s(context.get("session_id"))
    persisted = _load_persisted_session(session_id)
    if persisted:
        return persisted, True
    result_session = d(d(result).get("session"))
    if result_session:
        return result_session, False
    override = d(context.get("session_override"))
    if override:
        return override, False
    return {}, False


def _attach_hook_status(result: dict[str, Any], *, attached: bool, persisted: bool = False, error: str = "") -> dict[str, Any]:
    hook_status: dict[str, Any] = {
        "format_version": HOOK_FORMAT_VERSION,
        "attached": attached,
        "deterministic": True,
        "presentation_only": True,
    }
    if attached:
        hook_status.update({"persisted": persisted, "state_path": "runtime_state.turn_memory"})
    if error:
        hook_status["error"] = error
    result["turn_memory_runtime_hook"] = hook_status
    nested = d(result.get("result"))
    if nested:
        nested["turn_memory_runtime_hook"] = dict(hook_status)
        result["result"] = nested
    return result


def attach_turn_memory_to_runtime_result(result: dict[str, Any], *, call_context: Mapping[str, Any]) -> dict[str, Any]:
    """Attach deterministic recent/dialogue memory to an interactive turn result."""

    if not isinstance(result, dict):
        return result
    context = d(call_context)
    try:
        session, can_persist = _select_memory_session(result, context)
        updated_result, updated_session = attach_turn_memory_context_with_session(
            result,
            session=session,
            player_input=s(context.get("player_input")),
        )
        persisted = _save_persisted_session(updated_session, session_id=s(context.get("session_id"))) if can_persist else False
        return _attach_hook_status(updated_result, attached=True, persisted=persisted)
    except Exception as exc:
        return _attach_hook_status(result, attached=False, error=f"{type(exc).__name__}: {exc}")


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
            context = _extract_call_context(args, kwargs)
            return attach_turn_memory_to_runtime_result(result, call_context=context)
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
